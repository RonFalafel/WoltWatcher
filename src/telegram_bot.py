"""
Define the Telegram bot version of WebsiteWatcher
"""

import json
import logging
import re
from configuration import Configuration
from restaurant_watch import RestaurantWatch, RestaurantWatchlist

from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from wolt_api import find_restaurant, get_restaurant_status, resolve_wolt_url

class Bot:
    """ A Telegram Bot to watch and alert for URL changes """
    async def run_watch(self, context):
        """Run a round of WatcherManager and report any changes

        Args:
            self (Bot): The bot class
            context (telegram.ext.callbackcontext.CallbackContext): Object used for interaction with Telegram
        """
        logging.debug('Running watchlist check...')
        for watcher in self.watchlist.get_watchers():
            online, name, url = await get_restaurant_status(watcher.slug)
            watcher.times_checked += 1
            logging.debug(f'Query for {watcher.chat_id}: {name} is {"Online" if online else "Offline"}')
            if online:
                message = f"✅ {name} is online! Get your food from {url}"
                await context.bot.send_message(chat_id=watcher.chat_id, text=message)
                self.watchlist.remove(watcher.chat_id)
                continue
            
            if not watcher.is_muted:
                message = f"❌ {name} is still offline 😞"
                await context.bot.send_message(chat_id=watcher.chat_id, text=message)

            max_runs = watcher.max_runs if watcher.max_runs is not None else self.runs_before_giving_up
            if watcher.times_checked > max_runs:
                message = f"⌛ {name} was offline for too long, giving up.\n\n"
                message += "If you want, you can run me again."
                await context.bot.send_message(chat_id=watcher.chat_id, text=message)
                self.watchlist.remove(watcher.chat_id)
        logging.info('Done with watchlist')

    async def say_hello(self, update, context):
        """ Introduce yourself """
        logging.debug(f'Got /start command from chat id {update.message.chat_id}')

        await context.bot.send_message(
            chat_id=update.message.chat_id,
            text="Hey! To start, send me a link to an offline wolt restaurant!"
        )

    async def handle_single_restaurant(self, context, chat_id, restaurant):
        if restaurant['online']:
            message = f"✅ {restaurant['name']} is online! Get your food from {restaurant['url']}"
            await context.bot.send_message(chat_id=chat_id, text=message)
            return

        message = text=f"Let's go! I will now check {restaurant['name']} every {self.tick_frequency} seconds.\n"
        message += f"In the meantime, checkout the menu at {restaurant['url']}"

        await context.bot.send_message(chat_id, message)

        custom_max_runs = self.user_timeouts.get(chat_id)
        watch = RestaurantWatch(chat_id, restaurant['slug'], custom_max_runs)
        self.watchlist.add(watch)

    async def handle_multiple_restaurants(self, update, results):
        options = []
        options_caption = 'Choose Venue:\n'
        for idx, restaurant in enumerate(results):
            options.append(
                InlineKeyboardButton(f"{idx + 1}", callback_data=restaurant['slug'])
            )
            options_caption += f"{idx + 1}. {restaurant['name']} ({restaurant['address']})\n"

        markup = InlineKeyboardMarkup([options])
        await update.message.reply_text(options_caption, reply_markup=markup)
    
    async def handle_find_restaurants_results(self, update, context, chat_id, find_results):
        if len(find_results) == 1 and find_results[0].get('error') == '404':
            await context.bot.send_message(
                chat_id=chat_id,
                text="Restaurant not found (404)! The link might be invalid, or the restaurant may have been removed from Wolt."
            )
            return

        if len(find_results) == 0:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"No such restaurant found :("
            )
            return

        if len(find_results) != 1:
            return await self.handle_multiple_restaurants(update, find_results)

        restaurant = find_results[0]
        await self.handle_single_restaurant(context, chat_id, restaurant)

    async def handle_choice(self, update, context):
        query = update.callback_query
        await query.answer()

        message_chat_id = update.callback_query.message.chat.id

        slug = query.data
        restaurant_names = await find_restaurant(slug, self.restaurant_filters, True)
        await self.handle_find_restaurants_results(update, context, message_chat_id, restaurant_names)

    async def free_text(self, update, context):
        try:
            sender = update.message.chat.username
            raw_text = update.message.text
            
            # Clean up hidden formatting characters (like U+2060 Word Joiner) from copy-pasting
            text = ''.join(c for c in raw_text if c.isprintable() or c.isspace()).strip()
            
            logging.warning(f'{sender} sent text: {text[:100]}')
            
            # Extract the URL from the text, handling if the user pasted a message + link
            url_match = re.search(r'(https://wolt\.com/\S+)', text)
            if not url_match:
                await context.bot.send_message(
                    chat_id=update.message.chat_id,
                    text="Searching by name is currently disabled due to Wolt API changes. Please send a direct link to the restaurant instead!"
                )
                return

            wolt_url = url_match.group(1).rstrip('.,:;!?')
            slug = resolve_wolt_url(wolt_url)
            restaurant_names = await find_restaurant(slug, self.restaurant_filters, True)
            await self.handle_find_restaurants_results(update, context, update.message.chat_id, restaurant_names)
        except Exception as e:
            logging.error(f'[free_text] Error: {e}')
            await context.bot.send_message(
                chat_id=update.message.chat_id,
                text=f"No such restaurant found :("
            )

    async def unmute(self, update, context):
        users_watcher = self.watchlist.get_watcher(update.message.chat_id)
        if users_watcher:
            users_watcher.is_muted = False
            await context.bot.send_message(
                chat_id=update.message.chat_id,
                text="Unmuted! I will now let you know on each check if the restaurant is offline or online!"
            )
        else:
            await context.bot.send_message(
                chat_id=update.message.chat_id,
                text="You need to set a watch first!"
            )

    async def mute(self, update, context):
        users_watcher = self.watchlist.get_watcher(update.message.chat_id)
        if users_watcher:
            users_watcher.is_muted = True
            await context.bot.send_message(
                chat_id=update.message.chat_id,
                text="Muted! I will only text you when the restaurant is online!"
            )
        else:
            await context.bot.send_message(
                chat_id=update.message.chat_id,
                text="You need to set a watch first!"
            )    
    
    async def help_command(self, update, context):
        help_text = (
            "Here's how to use WoltWatcher:\n\n"
            "1. Send me a Wolt restaurant link (e.g., https://wolt.com/en/isr/tel-aviv/restaurant/gdb).\n"
            "2. I will monitor the restaurant and send you a message when it accepts orders again.\n\n"
            "Available commands:\n"
            "/start - Start the bot\n"
            "/help - Show this help message\n"
            "/mute - Mute notifications while checking (only notify when online)\n"
            "/unmute - Unmute notifications (notify if still offline on each check)\n"
            "/timeout <minutes> - Set a custom timeout before giving up (default: 2 hours)"
        )
        await context.bot.send_message(
            chat_id=update.message.chat_id,
            text=help_text
        )

    async def timeout(self, update, context):
        try:
            if not context.args:
                await context.bot.send_message(
                    chat_id=update.message.chat_id,
                    text="Please provide a timeout in minutes. Example: /timeout 60"
                )
                return
            
            minutes = int(context.args[0])
            if minutes <= 0:
                await context.bot.send_message(
                    chat_id=update.message.chat_id,
                    text="Timeout must be a positive number."
                )
                return

            max_runs = int((minutes * 60) / self.tick_frequency)
            self.user_timeouts[update.message.chat_id] = max_runs
            
            users_watcher = self.watchlist.get_watcher(update.message.chat_id)
            if users_watcher:
                users_watcher.max_runs = max_runs
                
            await context.bot.send_message(
                chat_id=update.message.chat_id,
                text=f"Timeout set to {minutes} minutes."
            )
        except ValueError:
            await context.bot.send_message(
                chat_id=update.message.chat_id,
                text="Invalid format. Please provide a number of minutes. Example: /timeout 60"
            )

    async def start(self, update, context):
        await context.bot.send_message(
            chat_id=update.message.chat_id,
            text="Hey! To start, send me a link to a restaurant or enter its name! Type /help for more information and commands."
        )
    
    def run_bot(self):
        """ Run the bot and wait for messages """
        logging.info('Bot started! Waiting for messages...')
        self.application.run_polling()

    def __init__(self, config: Configuration):
        """ Initialize the bot

        Args:
            config (Configuration): Contains the telegram bot's configuration
        """
        logging.debug('Registering with Telegram...')

        self.bot_password = config.password
        self.tick_frequency = config.tick_frequency
        
        # Override config's default timeout to 2 hours
        self.runs_before_giving_up = int(7200 / self.tick_frequency) if self.tick_frequency else 120
        
        self.restaurant_filters = config.filters
        self.watchlist = RestaurantWatchlist()
        self.user_timeouts = {}

        self.application = ApplicationBuilder().token(config.token).build()
        self.application.add_handler(CommandHandler('start', self.start))
        self.application.add_handler(CommandHandler('help', self.help_command))
        self.application.add_handler(CommandHandler('mute', self.mute))
        self.application.add_handler(CommandHandler('unmute', self.unmute))
        self.application.add_handler(CommandHandler('timeout', self.timeout))
        self.application.add_handler(MessageHandler(filters.TEXT, self.free_text))
        self.application.add_handler(CallbackQueryHandler(self.handle_choice))

        self.application.job_queue.run_repeating(self.run_watch, self.tick_frequency)