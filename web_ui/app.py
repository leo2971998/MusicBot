import threading
import asyncio
import os
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)


INDEX_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MusicBot Web UI</title>
    <style>
        /* CSS Variables for Theme Colors */
        :root {
            --bg-color: #ffffff;
            --text-color: #333333;
            --secondary-text: #666666;
            --border-color: #e0e0e0;
            --input-bg: #ffffff;
            --input-border: #ccc;
            --button-bg: #007bff;
            --button-hover: #0056b3;
            --button-text: #ffffff;
            --card-bg: #f8f9fa;
            --shadow: rgba(0, 0, 0, 0.1);
            --toggle-bg: #ccc;
            --toggle-circle: #ffffff;
        }

        [data-theme="dark"] {
            --bg-color: #1a1a1a;
            --text-color: #e0e0e0;
            --secondary-text: #b0b0b0;
            --border-color: #333333;
            --input-bg: #2d2d2d;
            --input-border: #555555;
            --button-bg: #0d6efd;
            --button-hover: #0b5ed7;
            --button-text: #ffffff;
            --card-bg: #2d2d2d;
            --shadow: rgba(0, 0, 0, 0.3);
            --toggle-bg: #555555;
            --toggle-circle: #ffffff;
        }

        /* Global Styles */
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            line-height: 1.6;
            transition: background-color 0.3s ease, color 0.3s ease;
        }

        .container {
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }

        /* Header */
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid var(--border-color);
        }

        h1 {
            color: var(--text-color);
            font-size: 2rem;
            font-weight: 600;
        }

        /* Theme Toggle */
        .theme-toggle {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .theme-toggle label {
            font-size: 0.9rem;
            color: var(--secondary-text);
        }

        .toggle-switch {
            position: relative;
            width: 50px;
            height: 25px;
            background-color: var(--toggle-bg);
            border-radius: 25px;
            cursor: pointer;
            transition: background-color 0.3s ease;
        }

        .toggle-switch::before {
            content: '';
            position: absolute;
            width: 21px;
            height: 21px;
            background-color: var(--toggle-circle);
            border-radius: 50%;
            top: 2px;
            left: 2px;
            transition: transform 0.3s ease;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
        }

        [data-theme="dark"] .toggle-switch::before {
            transform: translateX(25px);
        }

        .toggle-icons {
            display: flex;
            align-items: center;
            gap: 5px;
        }

        .toggle-icons span {
            font-size: 1.2rem;
        }

        /* Cards */
        .card {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px var(--shadow);
            transition: background-color 0.3s ease, border-color 0.3s ease;
        }

        .card h2 {
            margin-bottom: 15px;
            color: var(--text-color);
            font-size: 1.3rem;
        }

        /* Guild Info */
        .guild-info {
            background-color: var(--card-bg);
            padding: 15px;
            border-radius: 6px;
            margin-bottom: 20px;
            border-left: 4px solid var(--button-bg);
        }

        .guild-info p {
            color: var(--secondary-text);
            font-size: 0.9rem;
        }

        /* Queue List */
        .queue-list {
            list-style: none;
        }

        .queue-list li {
            padding: 10px;
            margin-bottom: 8px;
            background-color: var(--bg-color);
            border: 1px solid var(--border-color);
            border-radius: 4px;
            transition: background-color 0.3s ease;
        }

        .queue-list li:hover {
            background-color: var(--card-bg);
        }

        .queue-list li:empty {
            font-style: italic;
            color: var(--secondary-text);
        }

        /* Forms */
        .form-group {
            margin-bottom: 15px;
        }

        .form-group label {
            display: block;
            margin-bottom: 5px;
            font-weight: 500;
            color: var(--text-color);
        }

        input[type="text"] {
            width: 100%;
            padding: 12px;
            border: 1px solid var(--input-border);
            border-radius: 6px;
            background-color: var(--input-bg);
            color: var(--text-color);
            font-size: 16px;
            transition: border-color 0.3s ease, background-color 0.3s ease;
        }

        input[type="text"]:focus {
            outline: none;
            border-color: var(--button-bg);
            box-shadow: 0 0 0 3px rgba(13, 110, 253, 0.25);
        }

        button {
            background-color: var(--button-bg);
            color: var(--button-text);
            border: none;
            padding: 12px 24px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 16px;
            font-weight: 500;
            transition: background-color 0.3s ease;
        }

        button:hover {
            background-color: var(--button-hover);
        }

        button:active {
            transform: translateY(1px);
        }

        /* Status Messages */
        .no-guild {
            text-align: center;
            color: var(--secondary-text);
            font-style: italic;
            padding: 40px 20px;
        }

        .empty-queue {
            text-align: center;
            color: var(--secondary-text);
            font-style: italic;
            padding: 20px;
        }

        /* Responsive Design */
        @media (max-width: 600px) {
            .container {
                padding: 15px;
            }

            .header {
                flex-direction: column;
                gap: 15px;
                text-align: center;
            }

            h1 {
                font-size: 1.5rem;
            }

            .card {
                padding: 15px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎵 MusicBot Web UI</h1>
            <div class="theme-toggle">
                <div class="toggle-icons">
                    <span>☀️</span>
                    <div class="toggle-switch" onclick="toggleTheme()"></div>
                    <span>🌙</span>
                </div>
            </div>
        </div>

        {% if guild_id %}
            <div class="guild-info">
                <p><strong>Guild ID:</strong> {{ guild_id }}</p>
            </div>

            <div class="card">
                <h2>🎵 Current Queue</h2>
                {% if queue %}
                    <ul class="queue-list">
                        {% for item in queue %}
                            <li><strong>{{ loop.index }}.</strong> {{ item.title }}</li>
                        {% endfor %}
                    </ul>
                    <p style="margin-top: 15px; color: var(--secondary-text); font-size: 0.9rem;">
                        Total songs: {{ queue|length }}
                    </p>
                {% else %}
                    <div class="empty-queue">
                        <p>No songs queued.</p>
                    </div>
                {% endif %}
            </div>
        {% else %}
            <div class="card">
                <div class="no-guild">
                    <h2>🎵 Welcome to MusicBot</h2>
                    <p>Please specify a guild_id in the URL to view the queue.</p>
                    <p style="margin-top: 10px; font-size: 0.9rem;">
                        Example: <code>?guild_id=YOUR_GUILD_ID</code>
                    </p>
                </div>
            </div>
        {% endif %}

        <div class="card">
            <h2>➕ Add Song</h2>
            <form method="post" action="/play_form">
                <div class="form-group">
                    <label for="guild_id">Guild ID:</label>
                    <input type="text" 
                           id="guild_id"
                           name="guild_id" 
                           placeholder="Enter your Discord server's Guild ID" 
                           value="{{ guild_id or '' }}">
                </div>
                <div class="form-group">
                    <label for="query">Song:</label>
                    <input type="text" 
                           id="query"
                           name="query" 
                           placeholder="Enter song name, YouTube URL, or search query" 
                           required>
                </div>
                <button type="submit">🎵 Add to Queue</button>
            </form>
        </div>
    </div>

    <script>
        // Theme Management
        function initializeTheme() {
            const savedTheme = localStorage.getItem('musicbot-theme');
            const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            
            const theme = savedTheme || (systemPrefersDark ? 'dark' : 'light');
            document.documentElement.setAttribute('data-theme', theme);
        }

        function toggleTheme() {
            const currentTheme = document.documentElement.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('musicbot-theme', newTheme);
        }

        // Initialize theme on page load
        document.addEventListener('DOMContentLoaded', initializeTheme);

        // Listen for system theme changes
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
            if (!localStorage.getItem('musicbot-theme')) {
                document.documentElement.setAttribute('data-theme', e.matches ? 'dark' : 'light');
            }
        });
    </script>
</body>
</html>
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