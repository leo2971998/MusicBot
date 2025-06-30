import threading
import asyncio
import os
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)


INDEX_TEMPLATE = """
<!doctype html>
<title>MusicBot Web UI</title>
<h1>MusicBot Web UI</h1>
{% if guild_id %}
  <p>Guild ID: {{ guild_id }}</p>
  <h2>Queue</h2>
  <ul>
    {% for item in queue %}
      <li>{{ loop.index }}. {{ item.title }}</li>
    {% else %}
      <li>No songs queued.</li>
    {% endfor %}
  </ul>
{% else %}
  <p>No guild_id specified.</p>
{% endif %}

<h2>Add Song</h2>
<form method="post" action="/play_form">
  <input type="text" name="guild_id" placeholder="Guild ID" value="{{ guild_id or '' }}">
  <input type="text" name="query" placeholder="Song URL or search" required>
  <button type="submit">Play</button>
</form>
"""


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


@app.route("/")
def index():
    guild_id = request.args.get("guild_id")
    queue = []
    if guild_id:
        from bot_state import queue_manager
        queue = queue_manager.get_queue(str(guild_id))
    return render_template_string(INDEX_TEMPLATE, guild_id=guild_id, queue=queue)


@app.route('/queue/<int:guild_id>')
def get_queue(guild_id):
    from bot_state import queue_manager
    queue = queue_manager.get_queue(str(guild_id))
    return jsonify(queue)


@app.route('/play', methods=['POST'])
def play_song():
    data = request.json or {}
    result, status = play_song_view(data)
    return jsonify(result), status


@app.route('/play_form', methods=['POST'])
def play_song_form():
    guild_id = request.form.get('guild_id')
    query = request.form.get('query')
    data = {'guild_id': guild_id, 'query': query}
    play_song_view(data)
    from flask import redirect, url_for
    return redirect(url_for('index', guild_id=guild_id))


def play_song_view(data):
    guild_id = data.get('guild_id')
    query = data.get('query')
    if guild_id is None or query is None:
        return {'error': 'guild_id and query are required'}, 400

    from bot_state import client, queue_manager, player_manager, data_manager
    from commands.music_commands import process_play_request

    guild = client.get_guild(int(guild_id))
    if not guild:
        return {'error': 'Invalid guild_id'}, 400

    guild_id_str = str(guild_id)
    channel_id = client.guilds_data.get(guild_id_str, {}).get('channel_id')
    if not channel_id:
        return {'error': 'Bot is not set up in this guild'}, 400

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
    return {'message': result}, 200



