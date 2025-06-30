import threading
import asyncio
import os
from flask import Flask, request, jsonify

app = Flask(__name__)


def start_web_ui(host: str = "0.0.0.0", port: int = 8080):
    """Start the web UI in a separate thread.

    The ``WEB_UI_HOST`` and ``WEB_UI_PORT`` environment variables override the
    provided ``host`` and ``port`` arguments so you can easily configure the
    address in deployments (e.g. pm2).
    """
    host = os.getenv("WEB_UI_HOST", host)
    port = int(os.getenv("WEB_UI_PORT", str(port)))
    thread = threading.Thread(
        target=lambda: app.run(host=host, port=port, debug=False, use_reloader=False),
        daemon=True,
    )
    thread.start()


@app.route('/queue/<int:guild_id>')
def get_queue(guild_id):
    from bot_state import queue_manager
    queue = queue_manager.get_queue(str(guild_id))
    return jsonify(queue)


@app.route('/play', methods=['POST'])
def play_song():
    data = request.json or {}
    guild_id = data.get('guild_id')
    query = data.get('query')
    if guild_id is None or query is None:
        return jsonify({'error': 'guild_id and query are required'}), 400

    from bot_state import client, queue_manager, player_manager, data_manager
    from commands.music_commands import process_play_request

    guild = client.get_guild(int(guild_id))
    if not guild:
        return jsonify({'error': 'Invalid guild_id'}), 400

    guild_id_str = str(guild_id)
    channel_id = client.guilds_data.get(guild_id_str, {}).get('channel_id')
    if not channel_id:
        return jsonify({'error': 'Bot is not set up in this guild'}), 400

    channel = client.get_channel(int(channel_id))
    user = guild.me

    coro = process_play_request(
        user,
        guild,
        channel,
        query,
        client,
        queue_manager,
        player_manager,
        data_manager,
    )

    future = asyncio.run_coroutine_threadsafe(coro, client.loop)
    result = future.result()
    return jsonify({'message': result})

