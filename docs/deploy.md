# Secure Deployment Guide for TelegramAI

This guide describes how to configure a secure, automated deployment pipeline for **TelegramAI** on an Ubuntu server using GitHub Actions, Docker, and a dedicated, non-privileged system user.

---

## Architecture Overview

```mermaid
graph LR
    GitHub[GitHub Repo] -->|Actions Triggered| CD[CD Pipeline]
    CD -->|SSH Connection| Server[Ubuntu VPS]
    subgraph Server Setup
        Deployer[deployer user] -->|Runs docker commands| Docker[Docker Engine]
        Deployer -->|Pulls code| Git[Git Repo]
    end
```

By deploying through a dedicated `deployer` user without `sudo` access, you isolate your server's administrative capabilities. If the deployment key or user account is compromised, the attacker cannot gain root access or execute arbitrary administration tasks outside of Docker.

---

## Step 1: Create a Secure Non-Root Deployer User

1. Log in to your Ubuntu server as a root or a sudo-privileged user:
   ```bash
   ssh root@your-server-ip
   ```

2. Create a new system user named `deployer` without sudo privileges:
   ```bash
   sudo adduser --disabled-password --gecos "" deployer
   ```
   *Note: Using `--disabled-password` prevents password-based logins, forcing key-only authentication.*

3. Create the `.ssh` folder and configure directory permissions:
   ```bash
   sudo mkdir -p /home/deployer/.ssh
   sudo chmod 700 /home/deployer/.ssh
   sudo touch /home/deployer/.ssh/authorized_keys
   sudo chmod 600 /home/deployer/.ssh/authorized_keys
   sudo chown -R deployer:deployer /home/deployer/.ssh
   ```

---

## Step 2: Configure Docker Permissions

To allow the `deployer` user to manage containers and run Docker commands without requiring `sudo` privileges, add them to the `docker` group.

1. Add `deployer` to the `docker` group:
   ```bash
   sudo usermod -aG docker deployer
   ```

2. Verify that Docker is running and the group is active:
   ```bash
   sudo systemctl status docker
   ```

---

## Step 3: Generate and Configure SSH Keys

To establish a secure, passwordless connection from GitHub Actions to your server, you need to use an SSH Key.

1. Generate a secure SSH key pair on your local machine or target server:
   ```bash
   ssh-keygen -t ed25519 -C "github-actions-deployer" -f ~/.ssh/id_ed25519_deployer
   ```
   *Do not set a passphrase for this key, as GitHub Actions needs to use it automatically.*

2. Copy the content of the public key (`~/.ssh/id_ed25519_deployer.pub`) and append it to `/home/deployer/.ssh/authorized_keys` on your Ubuntu server:
   ```bash
   # Paste the public key string into this file:
   nano /home/deployer/.ssh/authorized_keys
   ```

3. Ensure correct permissions on the authorized_keys file:
   ```bash
   sudo chown deployer:deployer /home/deployer/.ssh/authorized_keys
   sudo chmod 600 /home/deployer/.ssh/authorized_keys
   ```

---

## Step 4: Clone the Repository on the Server

1. Switch to the `deployer` user on your server:
   ```bash
   sudo su - deployer
   ```

2. Clone your repository into the `deployer` home directory:
   ```bash
   git clone https://github.com/your-username/TelegramAI.git /home/deployer/TelegramAI
   ```
   *(If your repository is private, you can set up a GitHub Deploy Key for this specific repository. See GitHub's documentation on [Deploy Keys](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys#deploy-keys) for details).*

> [!NOTE]
> You do **not** need to manually create or edit the `.env` file on the server. The GitHub Actions CD pipeline automatically generates a secure `.env` file inside `/home/deployer/TelegramAI` during every deploy using your GitHub Environment variables, and applies `chmod 600` so that only the `deployer` user can access them.

---

## Step 5: Configure GitHub Environment and Secrets/Variables

To isolate environment configurations, this project uses GitHub Environments.

1. In your GitHub repository, navigate to **Settings > Environments**.
2. Click **New environment** and name it precisely: `BRIGE Help Bot`.
3. Under the **BRIGE Help Bot** environment settings, configure the following:

### Environment Secrets (Sensitive Data)

Add these under **Environment secrets**:

| Secret Name | Value Example | Description |
|---|---|---|
| `SSH_HOST` | `198.51.100.50` | The public IP address or domain of your Ubuntu server. |
| `SSH_USER` | `deployer` | The SSH deployment username (`deployer`). |
| `SSH_PRIVATE_KEY` | `-----BEGIN OPENSSH PRIVATE KEY-----...` | The entire content of your private SSH key (`id_ed25519_deployer`). |
| `WORK_DIR` | `/home/deployer/TelegramAI` | The exact path where the repo was cloned on the server. |
| `TELEGRAM_TOKEN` | `123456789:ABCDefGhI...` | Your Telegram Bot token from @BotFather. |
| `GEMINI_API_KEY` | `AIzaSy...` | Your Google AI Studio Gemini API Key. |
| `HF_TOKEN` | `hf_...` | (Optional) Your Hugging Face User Access Token. |

### Environment Variables (Non-Sensitive Configs)

Add these under **Environment variables**:

| Variable Name | Value Example | Description |
|---|---|---|
| `GEMINI_MODEL` | `gemini-3.1-flash-lite` | The name of the Gemini model to use. |
| `USE_GPU` | `false` | Whether to enable GPU support (set to `true` or `false`). |

## Step 6: Test the Deployment

Once all configurations are complete, you can trigger the CD pipeline:

1. Push your changes to the `main` branch.
2. Go to the **Actions** tab of your GitHub repository.
3. You should see the **CD Pipeline (Deploy)** running.
4. The workflow will securely connect to your VPS, pull the latest code, and execute:
   ```bash
   make deploy
   ```
   This will rebuild the Docker images and run the bot in the background (`-d`) automatically.

### Verification Commands on the Server

You can check the running containers and logs on your server as the `deployer` user:

- Check running containers:
  ```bash
  docker compose ps
  ```
- Follow real-time logs:
  ```bash
  make logs
  ```
- Stop the bot:
  ```bash
  make down
  ```
