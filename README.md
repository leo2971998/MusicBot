# MusicBot

A Python-based Discord Music Bot that allows users to play and manage audio tracks directly from their Discord server. This project leverages Python libraries and Discord’s API to create a seamless music experience, including features such as audio playback, queue management, and both command-based and button-based music controls.

## Demo

Below is a screenshot demonstrating the MusicBot’s UI with button controls:

![image](https://github.com/user-attachments/assets/c7b26006-290a-4408-ba8c-47a70db00c96)

*Example of how the queue and controls are displayed in a Discord channel.*

## Features

- **Play music** from various sources (e.g., YouTube)
- **Queue management** for multiple songs
- **Playback controls** (play, pause, skip, stop)
- **Button-based interactions** for users who prefer a graphical interface
- **Command-based interface** for users who prefer text commands
- **Easy configuration** through environment variables or a config file
- **Works across multiple guilds** with isolated queues
- **Auto disconnect** when idle (default 2 minutes, resets whenever new music is queued)

## Button-Based Usage

In addition to traditional text commands, MusicBot offers interactive buttons. Once a song is playing, the bot will display a set of buttons for quick control:

- **Play / Resume:** Resumes music if paused.  
- **Pause:** Pauses current playback.  
- **Skip:** Skips to the next song in the queue.  
- **Stop:** Stops the current song and clears the queue.  
- **Queue:** Displays the list of songs currently in the queue.  

Simply click the corresponding button in the bot’s message to perform that action—no need to type commands!

> **Note:** Button-based interactions require you to implement [Discord Interactions](https://discord.com/developers/docs/interactions) or a library that supports them. Ensure that you have set up the necessary code to handle these button clicks in your bot’s event handlers.

## Command-Based Usage

If you prefer text commands, or if button-based interactions are unavailable for any reason, you can still manage the bot using commands:

- **!play [song_name_or_link]** – Plays a specific song, automatically fetching from YouTube or your configured source.  
- **!pause** – Pauses current playback.  
- **!resume** – Resumes paused playback.  
- **!skip** – Skips to the next song in the queue.  
- **!stop** – Stops playback and clears the queue.  
- **!queue** – Shows the current list of songs queued.  

## Getting Started

1. **Clone this Repository**  
   ```bash
   git clone https://github.com/leo2971998/MusicBot.git
   ```

2. **Create a Virtual Environment (recommended)**  
   ```bash
   cd MusicBot
   python -m venv venv
   source venv/bin/activate    # For Linux/Mac
   venv\Scripts\activate       # For Windows
   ```

3. **Install Dependencies**  
   ```bash
   pip install -r requirements.txt
   ```

4. **Configuration**  
   - **Create a Discord Application** on the [Discord Developer Portal](https://discord.com/developers/applications).  
   - **Add a Bot User** to your application and copy your Bot Token.
   - **Enable the Voice States Gateway Intent** in the Developer Portal so the bot can manage voice connections properly.
   - **Verify Channel Permissions**:
     Ensure the bot has **Connect** and **Speak** permissions in every voice channel you intend to use. Check channel-level permission overwrites and grant a Stage Moderator role if using Discord Stage channels.
   - **Set Up a Configuration File** (e.g., `.env` or `config.json`) with the following:
     ```env
      DISCORD_BOT_TOKEN=YOUR_BOT_TOKEN
      # Optional: how long the bot stays in voice when idle
      IDLE_DISCONNECT_DELAY=120
      ```
      The timer is automatically cancelled if new songs are added before it expires.
    - Configure any additional settings as needed (e.g., prefix, default volume).

5. **Run the Bot**
   ```bash
   python -m bot
   ```

   Once the bot is running, invite it to your server using the OAuth2 link provided in the Discord Developer Portal.
