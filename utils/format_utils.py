def format_time(seconds):
    """Format seconds into MM:SS format"""
    try:
        minutes = int(seconds) // 60
        secs = int(seconds) % 60
        return f"{minutes:02d}:{secs:02d}"
    except (ValueError, TypeError):
        return "00:00"

def format_duration(duration):
    """Format duration with hours if needed"""
    try:
        total_seconds = int(duration)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"
    except (ValueError, TypeError):
        return "00:00"

def truncate_string(text, max_length=100):
    """Truncate string to max length with ellipsis"""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."