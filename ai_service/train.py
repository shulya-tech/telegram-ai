import json
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import LoraConfig
from trl import SFTTrainer, SFTConfig
from datasets import Dataset

# Define model and data paths
MODEL_NAME = "Qwen/Qwen2.5-0.5B-Instruct"
DATA_PATH = "../data/dataset.jsonl"
OUTPUT_DIR = "../data/models/qwen_lora"


def format_data_for_training(data_path):
    # Load JSONL data
    with open(data_path, "r", encoding="utf-8") as f:
        data = [json.loads(line) for line in f]

    formatted_data = []
    for item in data:
        messages = item.get("messages", [])
        if (
            len(messages) == 2
            and messages[0]["role"] == "user"
            and messages[1]["role"] == "assistant"
        ):
            user_msg = messages[0]["content"]
            assistant_msg = messages[1]["content"]

            # Format using Qwen's expected prompt structure (ChatML-like)
            text = f"<|im_start|>user\n{user_msg}<|im_end|>\n<|im_start|>assistant\n{assistant_msg}<|im_end|>"
            formatted_data.append({"text": text})

    return Dataset.from_list(formatted_data)


def main():
    print(f"Loading tokenizer {MODEL_NAME}...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token

    print("Preparing dataset...")
    dataset = format_data_for_training(DATA_PATH)

    print(f"Loading model {MODEL_NAME}...")
    device_map = "auto" if torch.cuda.is_available() else "cpu"

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        device_map=device_map,
        trust_remote_code=True,
        dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
    )

    # Configure LoRA
    print("Configuring LoRA...")
    peft_config = LoraConfig(
        r=8,
        lora_alpha=16,
        target_modules=["q_proj", "v_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )

    use_gpu = torch.cuda.is_available()
    if not use_gpu:
        torch.backends.mkldnn.enabled = False

    # Training arguments
    print("Setting up training arguments...")
    training_args = SFTConfig(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        logging_steps=10,
        max_steps=50,
        save_steps=50,
        fp16=use_gpu,
        use_cpu=not use_gpu,
        optim="adamw_torch",
        dataset_text_field="text",
        max_length=512,
    )

    # SFT Trainer
    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        peft_config=peft_config,
        processing_class=tokenizer,
        args=training_args,
    )

    print("Starting training...")
    trainer.train()

    print(f"Saving model to {OUTPUT_DIR}...")
    trainer.save_model(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    print("Training complete!")


if __name__ == "__main__":
    main()
