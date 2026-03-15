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
current_machine = ""
machine_notes = {}

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

def load_machine_notes():
    global machine_notes
    try:
        with open('machine_notes_submodule/machine_notes.json', 'r') as file:
            machine_notes = json.load(file)
    except FileNotFoundError:
        print("machine_notes.json file not found. Please ensure it exists.")

def save_machine_notes():
    global machine_notes
    try:
        with open('machine_notes_submodule/machine_notes.json', 'w') as file:
            json.dump(machine_notes, file, indent=2)
    except Exception as e:
        print(f"Error saving machine_notes.json: {e}")

"""
Splits the play duration into drill times rounded to the nearest 5 minutes.
The breakdown of play is as follows:
- 15% of the time for warmup/free play
- 35% of the time for drills
- 25% of the time for tournament simulation
- 10% of the time for score maximizing
- 15% of the time for cooldown/free play
"""
def build_practice_plan(duration):
    global drills
    # Calculate the time for each segment of the practice plan, rounded to the nearest 5 minutes
    warmup_time = round(duration * (.15) / 5) * 5
    drill_time = round(duration * (.35) / 5) * 5
    tournament_time = round(duration * (.25) / 5) * 5
    score_time = round(duration * (.10) / 5) * 5
    cooldown_time = round(duration * (.15) / 5) * 5

    # Create the practice plan
    practice_plan = [
        {"activity": "Warmup/Free Play", "duration": warmup_time},
        {"activity": "Skill Anchor Drills", "duration": drill_time, "drills": []},
        {"activity": "Tournament Simulation", "duration": tournament_time},
        {"activity": "Score Maximizing", "duration": score_time},
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
            tables_list = ',\n'.join(machines_at_location)
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Tables at {location}:\n{tables_list}")
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Location not found. Please try again.")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Please provide a location.")

"""Set the current machine being played."""
async def set_current_machine(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global play_location, current_machine

    if not play_location:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Please set your playing location first using /location.")
        return

    if context.args:
        machine_input = ' '.join(context.args).lower()
        machines_at_location = pb_map_api.get_machines_at_location(play_location)
        
        # Weak match: find machine if input is within machine name (case insensitive)
        matched_machine = None
        for machine in machines_at_location:
            if machine_input in machine.lower():
                matched_machine = machine
                break
        
        if matched_machine:
            current_machine = matched_machine
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Current machine set to: {current_machine}")
            await lookup_and_print_tips(update, context, current_machine)
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Machine '{' '.join(context.args)}' not found at {play_location['name']}.")
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Please provide a machine name.")

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

async def list_all_drills(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all the potential drills"""
    global drills
    if drills:
        message = "All drill options:\n"
        for drill in drills:
            message += f"- {drill['name']}: {drill['description']}\n"
        await context.bot.send_message(chat_id=update.effective_chat.id, text=message)


async def pick_random_table(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pick a random table from the user's location."""
    global play_location
    global current_machine
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
        while (random_table == current_machine) or (random_table is None):
            random_table = random.sample(machines_at_location, num_tables)
        current_machine = random_table[0]

        if num_tables > 1:
            tables_text = ',\n'.join(random_table)
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Random tables selected: {tables_text}")
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

async def lookup_and_print_tips(update: Update, context: ContextTypes.DEFAULT_TYPE, machine_name: str) -> None:
    """Helper function to print tips for a given machine name."""
    global play_location, machine_notes
    
    # Perform case-insensitive search, ignoring anything in parentheses
    lookup_name = machine_name.split('(')[0].strip()
    machine_key = None
    for key in machine_notes:
        if key.lower() == lookup_name.lower():
            machine_key = key
            break
    
    if machine_key:
        tips = machine_notes[machine_key]["tips"]
        message = f"Tips for {lookup_name}:\n"
        for tip in tips:
            # If the tip is location specific, and we are at that location, or of it is a general tip, print it
            if "location" in tip and play_location and "name" in play_location and tip["location"] in play_location["name"]:
                    message += f"- ({tip['location']}) {tip['text']}\n"
            else:
                message += f"- {tip['text']}\n"
        await context.bot.send_message(chat_id=update.effective_chat.id, text=message)
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"No tips found for {machine_name}.")

async def print_machine_tips(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Print machine-specific tips for the user's location."""
    global play_location, current_machine

    # Get the machine name from the first argument, otherwise grab it from the last random table
    if context.args:
        machine_name = ' '.join(context.args)
    elif current_machine:
        machine_name = current_machine
    #otherwise print an error
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Please provide a machine name or pick a random table first using /random.")
        return
    
    await lookup_and_print_tips(update, context, machine_name)

async def add_general_tip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add a general tip to the current machine."""
    global current_machine, machine_notes

    if not current_machine:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Please set a current machine first using /machine.")
        return

    if not context.args:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Please provide a tip to add.")
        return

    tip_text = ' '.join(context.args)
    
    # Add machine to machine_notes if it doesn't exist
    if current_machine not in machine_notes:
        machine_notes[current_machine] = {"tips": []}
    
    # Add the tip
    machine_notes[current_machine]["tips"].append({"text": tip_text})
    save_machine_notes()
    
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"General tip added to {current_machine}.")

async def add_location_tip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add a location-specific tip to the current machine."""
    global current_machine, play_location, machine_notes

    if not current_machine:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Please set a current machine first using /machine.")
        return

    if not play_location:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Please set your playing location first using /location.")
        return

    if not context.args:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Please provide a tip to add.")
        return

    tip_text = ' '.join(context.args)
    
    # Add machine to machine_notes if it doesn't exist
    if current_machine not in machine_notes:
        machine_notes[current_machine] = {"tips": []}
    
    # Add the location-specific tip
    machine_notes[current_machine]["tips"].append({
        "text": tip_text,
        "location_specific": True,
        "location": play_location["name"]
    })
    save_machine_notes()
    
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Location-specific tip added to {current_machine} for {play_location['name']}.")

async def bot_testprint(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    print("Test print from bot.py")
    # This function is just for testing purposes
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Test print from bot.py")

async def print_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_message = (
        "Available commands:\n"
        "/location or /l [location] - Set your playing location\n"
        "/duration or /d or /t [minutes] - Set your playing duration\n"
        "/random or /r [number] - Pick a random table from your location (optionally specify how many)\n"
        "/generate or /g - Generate a practice plan based on your location and duration\n"
        "/alldrills or /ad - List all potential drills\n"
        "/tips or /t [machine name] - Get tips for a specific machine (or the current machine if no name is provided)\n"
        "/machine or /m [machine name] - Set the current machine being played and get tips for it\n"
        "/gtip [tip text] - Add a general tip for the current machine\n"
        "/ltip [tip text] - Add a location-specific tip for the current machine\n"
        "/help or /h - Show this help message"
    )
    await context.bot.send_message(chat_id=update.effective_chat.id, text=help_message)

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
    load_machine_notes()

    # Create a bot instance with the bot token
    app = ApplicationBuilder().token(bot_token).build()
    app.add_handler(CommandHandler(("location", "l"), set_playing_location))
    app.add_handler(CommandHandler(("machine", "m"), set_current_machine))
    app.add_handler(CommandHandler(("duration", "d"), set_playing_duration))
    app.add_handler(CommandHandler(("random", "r"), pick_random_table))
    app.add_handler(CommandHandler(("generate", "g"), report_practice_plan))
    app.add_handler(CommandHandler(("alldrills", "ad"), list_all_drills))
    app.add_handler(CommandHandler(("tips", "t"), print_machine_tips))
    app.add_handler(CommandHandler("gtip", add_general_tip))
    app.add_handler(CommandHandler("ltip", add_location_tip))
    app.add_handler(CommandHandler(("help", "h"), print_help))
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
