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

# Optionally, if the API requires parameters, you can define them here
params = {
    # Example: 'location_id': '123', or any other params the API might need
    'region' : 'Reno, NV'
}

# Send a GET request to the API
#response = requests.get(base_url)

# Check if the request was successful (status code 200 means OK)
#if response.status_code == 200:
#    # Parse the JSON response
#    data = response.json()

#    print(json.dumps(data, indent=4))
#else:
#    print(f"Failed to fetch data: {response.status_code}")


"""
Sets the playing location for the user.
"""
async def set_playing_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set the playing location for the user."""
    # Extract the location from the command arguments
    if context.args:
        location = ' '.join(context.args)
        region = "reno"
        possible_location = pb_map_api.get_locations_in_region(region)
        machines_at_location = []
        # Find the closest location in the area that matches the user's input
        for lc in possible_location:
            if location.lower() in lc['name'].lower():
                location = lc['name']
                print (f"Location found: {location}")
                machines_at_location = pb_map_api.get_machines_at_location(lc)
                break

        # Here you would typically save the location to a database or user profile
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Playing location set to: {location}")
        #List the tables at the location
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Tables at {location}: {', '.join(machines_at_location)}")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Please provide a location.")


async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /hello is issued."""
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Hello!")

def main():
     # Read the bot token from the file
    with open('token.txt', 'r') as file:
        bot_token = file.read().strip()

    # Create a bot instance with the bot token
    app = ApplicationBuilder().token(bot_token).build()
    app.add_handler(CommandHandler("hello", hello))
    app.add_handler(CommandHandler("location", set_playing_location))

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
