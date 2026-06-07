# Adsgram Integration Guide

This guide explains how to register on Adsgram, create an Ad Block, set up Server-to-Server (S2S) reward callbacks, and configure Nginx to proxy incoming traffic to your bot's web server.

---

## 1. Registering on Adsgram

1. Go to the [Adsgram Publisher Dashboard](https://partner.adsgram.ai/).
2. Log in using your Telegram account.
3. In the left sidebar, click on **Platforms**.
4. Click **Add Platform** and select **Telegram Bot**.
5. Fill in your bot's details (username, category, description) and submit. Note that your bot must pass moderation before it can display live ads (during development, you can use test block IDs or developer sandbox modes).

---

## 2. Creating an Ad Block & Getting Unit ID

1. Once your platform is registered, click on it in the dashboard.
2. Click **Create Ad Block**.
3. Choose the **Rewarded Video** format (this requires users to watch the ad completely to receive their reward).
4. Save the block. You will get a unique **Block ID** (also called Unit ID), for example: `bot-34368`.

   > [!IMPORTANT]
   > The ID `bot-34368` is a special test block ID provided by Adsgram for testing and development. You must replace it with your actual production Block ID once your platform has been approved and moderated.

5. Copy this Block ID and add it to your `.env` file:
   ```env
   ADSGRAM_BLOCK_ID="bot-34368"
   ```

---

## 3. Configuring the Reward URL (S2S Callback)

To securely credit users after they finish watching an ad, Adsgram uses a Server-to-Server (S2S) Callback. To prevent unauthorized requests from minting quota, you must use a shared secret token.

1. **Generate a Shared Secret**: Create a random secure string of your choice (e.g., `my_secure_token_123`).
2. Go to your Ad Block settings in the Adsgram dashboard.
3. Find the **Reward URL** (or callback URL) field.
4. Enter your public HTTPS URL including both the `[userId]` placeholder and your custom secret token:
   ```
   https://your-domain.com/reward?userid=[userId]&secret=YOUR_SHARED_SECRET
   ```
   *(Replace `YOUR_SHARED_SECRET` with the exact string you generated in step 1).*
5. When a reward event occurs, Adsgram will invoke this endpoint, replacing `[userId]` with the Telegram ID but keeping your secret query parameter intact.


---

## 4. Bot Web Server Configuration

Update your `.env` configuration with the public base URL, local port, and your generated shared secret:

```env
# The public HTTPS URL of your server
BASE_URL="https://your-domain.com"

# The port where the python web server will bind locally
PORT=8080

# The shared secret token for verifying S2S callbacks
ADSGRAM_SECRET="YOUR_SHARED_SECRET"
```


---

## 5. Nginx Reverse Proxy Setup

Nginx must listen on port 443 (HTTPS) and forward incoming requests for the Mini App page (`/ad`) and the reward callback webhook (`/reward`) to your Python application.

Here is a template Nginx server block configuration:

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    # Redirect HTTP to HTTPS
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # SSL Certificate Configuration (e.g., Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Route for the Telegram Mini App (Loads the ad-serving HTML page)
    location /ad {
        proxy_pass http://127.0.0.1:8080/ad;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Disable caching for the Mini App page to ensure SDK updates load immediately
        add_header Cache-Control "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0";
    }

    # Route for the Adsgram Reward Callback webhook
    location /reward {
        proxy_pass http://127.0.0.1:8080/reward;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Applying Nginx configuration:
1. Save the configuration to `/etc/nginx/sites-available/telegram-bot.conf`.
2. Enable it: `sudo ln -s /etc/nginx/sites-available/telegram-bot.conf /etc/nginx/sites-enabled/`.
3. Test configuration: `sudo nginx -t`.
4. Reload Nginx: `sudo systemctl reload nginx` or `sudo service nginx reload`.

---

## 6. Testing the Setup

### Test the Reward Endpoint:
You can simulate a verified Adsgram callback request using `curl`:
```bash
curl "https://your-domain.com/reward?userid=YOUR_TELEGRAM_USER_ID&secret=YOUR_SHARED_SECRET"
```
If successful, your bot should immediately send a Telegram message to your account saying:
`🎉 You have successfully watched the ad! 5 requests have been added to your balance.`
And your balance will be increased by 5 requests (verify by calling `/my_plan` in the bot).

