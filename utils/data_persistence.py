# utils/helpers.py

def format_time(seconds):
    minutes = int(seconds) // 60
    seconds = int(seconds) % 60
    return f"{minutes:02d}:{seconds:02d}"

def create_progress_bar_emoji(elapsed, duration):
    if duration == 0:
        return ''
    total_blocks = 20  # Adjust the number of blocks as needed
    progress_percentage = (elapsed / duration) * 100
    progress_blocks = round((progress_percentage / 100) * total_blocks)
    bar = '▶️ ' + '🟩' * progress_blocks + '🟥' * (total_blocks - progress_blocks)
    return bar
