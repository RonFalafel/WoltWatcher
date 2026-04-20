### This is a fork of [Oz Tamir's WoltWatcher](https://github.com/OzTamir/WoltWatcher.git)

# WoltWatcher

A dockerized telegram bot to monitor Wolt restaurant and notify when they can take orders again.

Inspired by [slack_wolt_notifier](https://github.com/Fraysa/slack_wolt_notifier).

## How to use
0. Create your bot and get your Telegram token (using the [BotFather](https://telegram.me/BotFather))
1. Clone the repository locally:
```bash
git clone https://github.com/RonFalafel/WoltWatcher.git
```
2. Add a file named my_config.json and insert your telegram token:
```json
{
    "telegram_config" : {
        "token": "<your token here>",
        "password": "",
        "tick_frequency" : 60,
        "runs_before_giving_up": 15
    },
    "filters": {
        "currency" : ["ILS"]
    }
}
```
3. Build the Docker image from the directory:
```bash
docker build --tag wolt-watcher-bot:1.0 .
```
4. Run the continer:
```bash
docker run --detach --name wolt-watcher wolt-watcher-bot:1.0
```
5. Enjoy!

## Features

Once the bot is running, simply open a chat with it on Telegram:

1. Send `/start` to greet the bot.
2. Paste a direct Wolt restaurant link (e.g., `https://wolt.com/en/isr/tel-aviv/restaurant/gdb`).
3. The bot will continually monitor the page in the background and notify you the moment the restaurant begins accepting orders again!

### Available Commands
* `/help` - Show the help message and command list.
* `/mute` - Mute periodic offline updates (the bot will only message you when the restaurant finally goes online).
* `/unmute` - Unmute notifications (the bot will update you every time it checks and the restaurant is still offline).
* `/timeout <minutes>` - Set a custom timeout limit before the bot stops watching (Default is 2 hours).