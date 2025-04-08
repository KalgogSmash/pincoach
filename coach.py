import requests
import json
import signal
import sys
import asyncio
import pb_map_api
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Define the base URL for the API
pin_map_base_url = "https://pinballmap.com"
get_reno_locations = "/api/v1/region/reno/locations.json"  

play_location = {}
play_duration = 60 # Default play duration in minutes

"""
Sets the playing location for the user.
"""
async def set_playing_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global play_location

    """Set the playing location for the user."""
    # Extract the location from the command arguments
    if context.args:
        location = ' '.join(context.args)
        possible_location = pb_map_api.get_locations_in_region(region)
        machines_at_location = []
        # Find the closest location in the area that matches the user's input
        for lc in possible_location:
            if location.lower() in lc['name'].lower():
                play_location = lc['name']
                print (f"Location found: {play_location['name']}")
                machines_at_location = pb_map_api.get_machines_at_location(play_location)
                break

        # Here you would typically save the location to a database or user profile
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Playing location set to: {location}")
        #List the tables at the location
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Tables at {location}: {', '.join(machines_at_location)}")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Please provide a location.")

"""Set the playing duration for the user."""
async def set_playing_duration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global play_duration

    """Set the playing duration for the user."""
    # Extract the duration from the command arguments
    if context.args:
        try:
            duration = int(context.args[0])
            play_duration = duration
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Playing duration set to: {duration} minutes")
        except ValueError:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Please provide a valid number for the duration.")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Please provide a duration.")

def load_default_drills():
    # Load the default drills from drills.json
    try:
        with open('drills.json', 'r') as file:
            drills = json.load(file)
            return drills
    except FileNotFoundError:
        print("drills.json file not found. Please ensure it exists.")
        return {}

def main():
     # Read the bot token from the file
    with open('token.txt', 'r') as file:
        bot_token = file.read().strip()

    load_default_drills

    # Create a bot instance with the bot token
    app = ApplicationBuilder().token(bot_token).build()
    app.add_handler(CommandHandler("location", set_playing_location))
    app.add_handler(CommandHandler("duration", set_playing_duration))

    try:
        # Continuously poll for updates
        app.run_polling()
    except KeyboardInterrupt:
        # Handle Ctrl+C gracefully
        print("KeyboardInterrupt received. Exiting...")
        app.stop()
        sys.exit(0)

if __name__ == '__main__':
    main()
