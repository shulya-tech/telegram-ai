import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer
from peft import PeftModel
import threading
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

class LLMOrchestrator:

    def __init__(self, base_model_id="Qwen/Qwen2.5-0.5B-Instruct", lora_path="../data/models/qwen_lora"):
        self.base_model_id = base_model_id
        self.lora_path = lora_path
        self.model = None
        self.tokenizer = None
        self.load_lock = threading.Lock()


        # System prompt
        self.system_prompt = (
            "You are a helpful and intelligent AI Telegram Agent. "
            "You can answer any user questions. "
            "If the user sent a photo (the message contains [Photo: ...]), "
            "answer questions about the content of the image fully. "
            "Always respond in English."
        )


    def load(self):
        if self.model is not None:
            return
        with self.load_lock:
            if self.model is None:
                print(f"Loading LLM base model {self.base_model_id}...")
                device = "cuda" if torch.cuda.is_available() else "cpu"

                base_model = AutoModelForCausalLM.from_pretrained(
                    self.base_model_id,
                    trust_remote_code=True,
                    dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                    device_map=device,
                )
                self.tokenizer = AutoTokenizer.from_pretrained(self.base_model_id, trust_remote_code=True)

                import os
                lora_config = os.path.join(self.lora_path, "adapter_config.json")
                if os.path.exists(lora_config):
                    print(f"Applying LoRA weights from {self.lora_path}...")
                    self.model = PeftModel.from_pretrained(base_model, self.lora_path)
                else:
                    self.model = base_model

                print("LLM loaded.")

    def summarize(self, messages) -> str:
        self.load()

        conv_text = ""
        for msg in messages:
            if msg.role == "user":
                conv_text += f"User: {msg.content}\n"
            elif msg.role == "assistant":
                conv_text += f"Assistant: {msg.content}\n"

        summary_messages = [
            {"role": "system", "content": "You are an assistant that creates concise conversation summaries."},
            {"role": "user", "content": (
                "Create a brief summary of this conversation in English. "
                "Keep the key questions, facts, and answers:\n\n" + conv_text
            )},
        ]

        input_text = self.tokenizer.apply_chat_template(summary_messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer([input_text], return_tensors="pt").to(self.model.device)

        with torch.no_grad():
            output = self.model.generate(
                **inputs,
                max_new_tokens=256,
                temperature=0.3,
                do_sample=True,
                pad_token_id=self.tokenizer.eos_token_id,
            )

        new_tokens = output[0][inputs["input_ids"].shape[1]:]
        return self.tokenizer.decode(new_tokens, skip_special_tokens=True).strip()

    def generate_stream(self, messages, image_context=None):
        self.load()

        # Prepare LangChain messages
        # If there's a summary message, inject it into the system prompt
        summary_text = ""
        chat_messages = []
        for msg in messages:
            if msg.role == "summary":
                summary_text = msg.content
            else:
                chat_messages.append(msg)

        system_content = self.system_prompt
        if summary_text:
            system_content += f"\n\nSummary of the previous conversation:\n{summary_text}"

        lc_messages = [SystemMessage(content=system_content)]

        for msg in chat_messages:
            if msg.role == "user":
                content = msg.content
                if image_context and msg == chat_messages[-1]:
                    content += f"\n\n[Image description: {image_context}]"
                lc_messages.append(HumanMessage(content=content))
            elif msg.role == "assistant":
                lc_messages.append(AIMessage(content=msg.content))

        # Format for HuggingFace Chat Template
        hf_messages = []
        for msg in lc_messages:
            if isinstance(msg, SystemMessage):
                hf_messages.append({"role": "system", "content": msg.content})
            elif isinstance(msg, HumanMessage):
                hf_messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                hf_messages.append({"role": "assistant", "content": msg.content})

        input_text = self.tokenizer.apply_chat_template(hf_messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer([input_text], return_tensors="pt").to(self.model.device)

        streamer = TextIteratorStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True)

        generation_kwargs = dict(
            **inputs,
            streamer=streamer,
            max_new_tokens=512,
            temperature=0.7,
            top_p=0.95,
            repetition_penalty=1.1,
            do_sample=True,
            pad_token_id=self.tokenizer.eos_token_id,
        )

        thread = threading.Thread(target=self.model.generate, kwargs=generation_kwargs)
        thread.start()

        return streamer

llm_orchestrator = LLMOrchestrator()
