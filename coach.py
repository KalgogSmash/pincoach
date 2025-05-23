import requests
import json
import sys
import os
import pb_map_api
import random
import logging
import asyncio
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Define the base URL for the API
pin_map_base_url = "https://pinballmap.com"
get_reno_locations = "/api/v1/region/reno/locations.json"  

region = "reno"
play_location = {}
play_duration = 60 # Default play duration in minutes
drills = []
reminders = []
last_random_table = ""

def load_default_drills():
    global drills
    # Load the default drills from drills.json
    try:
        with open('drills.json', 'r') as file:
            drill_dict = json.load(file)
            drills =  drill_dict["drills"]
    except FileNotFoundError:
        print("drills.json file not found. Please ensure it exists.")
    
def load_default_reminders():
    global reminders
    try:
        with open('drills.json', 'r') as file:
            drill_dict = json.load(file)
            reminders = drill_dict["reminders"]
    except FileNotFoundError:
        print("drills.json file not found. Please ensure it exists.")

    
"""
Splits the play duration into drill times rounded to the nearest 5 minutes.
The breakdown of play is as follows:
- 1/6 of the time for warmup/free play
- 2/6 of the time for drills
- 2/6 of the time for tournament simulation
- 1/6 of the time for cooldown/free play
"""
def build_practice_plan(duration):
    global drills
    # Calculate the time for each segment of the practice plan, rounded to the nearest 5 minutes
    warmup_time = round(duration * (1/6) / 5) * 5
    drill_time = round(duration * (2/6) / 5) * 5
    tournament_time = round(duration * (2/6) / 5) * 5
    cooldown_time = round(duration * (1/6) / 5) * 5

    # Create the practice plan
    practice_plan = [
        {"activity": "Warmup/Free Play", "duration": warmup_time},
        {"activity": "Drills", "duration": drill_time, "drills": []},
        {"activity": "Tournament Simulation", "duration": tournament_time},
        {"activity": "Cooldown/Free Play", "duration": cooldown_time}
    ]

    ## Select random drills for the drill segment and pick a random table for each one 
    if drill_time > 0:
        # Select random drills from the drills list
        selected_drills = random.sample(drills, min(2, drill_time // 10))
        for drill in selected_drills:
            # Pick a random table for each drill
            table = pb_map_api.get_machines_at_location(play_location)
            if table:
                practice_plan[1]["drills"].append({"drill": drill, "table": random.choice(table)})
            else:
                print("No tables found at the selected location.")


    return practice_plan

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
        found = False

        # Find the closest location in the area that matches the user's input
        for lc in possible_location:
            if location.lower() in lc['name'].lower():
                play_location = lc
                found = True
                machines_at_location = pb_map_api.get_machines_at_location(play_location)
                break

        if found:
            # Here you would typically save the location to a database or user profile
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Playing location set to: {play_location['name']}")
            #List the tables at the location
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Tables at {location}:\n{',\n'.join(machines_at_location)}")
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Location not found. Please try again.")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Please provide a location.")

"""Set the playing duration for the user."""
async def set_playing_duration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global play_duration

    print("Setting playing duration...")

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
    
async def report_practice_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate a practice plan based on the user's location and duration."""
    global play_location, play_duration, drills

    # Check if the user has set a location and duration
    if not play_location:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Please set your playing location first using /location.")
        return

    if not play_duration:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Please set your playing duration first using /duration.")
        return
    
    # Build the practice plan
    practice_plan = build_practice_plan(play_duration)

    await context.bot.send_message(chat_id=update.effective_chat.id, text="Practice plan generated:")
    for segment in practice_plan:
        message = f"{segment['activity']} for {segment['duration']} minutes"
        if 'drills' in segment:
            for drill in segment['drills']:
                message += f"\n- {drill['drill']['name']} on {drill['table']}. {drill['drill']['description']}"
        await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

async def pick_random_table(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pick a random table from the user's location."""
    global play_location
    global last_random_table
    global reminders

    if not play_location:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Please set your playing location first using /location.")
        return

    # If the user provides a number as an argument, generate that many tables
    if context.args:
        try:
            num_tables = int(context.args[0])
            if num_tables < 1:
                await context.bot.send_message(chat_id=update.effective_chat.id, text="Please provide a positive number.")
                return
        except ValueError:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Please provide a valid number.")
            return
    else:
        num_tables = 1  # Default to 1 table if no argument is provided

    # Pick a random table from the location's machines
    machines_at_location = pb_map_api.get_machines_at_location(play_location)
    if machines_at_location:
        #randomize a table until it is different from the last one
        random_table = None
        while (random_table == last_random_table) or (random_table is None):
            random_table = random.sample(machines_at_location, num_tables)
        last_random_table = random_table[0]

        if num_tables > 1:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Random tables selected: {',\n'.join(random_table)}")
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Random table selected: {random_table[0]}")
        # Send a random reminder
        if reminders:
            random_reminder = random.choice(reminders)
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Reminder: {random_reminder}")
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="No reminders available.")
        
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="No tables found at the selected location.")

async def bot_testprint(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    print("Test print from bot.py")
    # This function is just for testing purposes
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Test print from bot.py")


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    print("Pincoach bot running. Performing initialization...")

    print("Current working directory:", os.getcwd())
    print("drills.json exists?", os.path.exists('drills.json'))
    print("token.txt exists?", os.path.exists('token.txt'))

     # Read the bot token from the file
    with open('token.txt', 'r') as file:
        bot_token = file.read().strip()

    load_default_drills()
    load_default_reminders()

    # Create a bot instance with the bot token
    app = ApplicationBuilder().token(bot_token).build()
    app.add_handler(CommandHandler("location", set_playing_location))
    app.add_handler(CommandHandler("duration", set_playing_duration))
    app.add_handler(CommandHandler("random", pick_random_table))
    app.add_handler(CommandHandler("generate", report_practice_plan))
    app.add_handler(CommandHandler("test", bot_testprint))

    try:
        # Continuously poll for updates
        app.run_polling()
    except KeyboardInterrupt:
        # Handle Ctrl+C gracefully
        print("KeyboardInterrupt received. Exiting...")
        app.stop()
        sys.exit(0)
    except Exception as e:
        # Handle other exceptions gracefully
        print(f"An error occurred: {e}")
        app.stop()
        sys.exit(1)

if __name__ == '__main__':
    main()
