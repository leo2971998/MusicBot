module.exports = {
  apps: [{
    name: 'musicbot',
    script: './bot.py',
    interpreter: '/home/leo29798/musicbot-env/bin/python',
    cwd: '/home/leo29798/MusicBot',
    env: {
      PYTHONUNBUFFERED: '1', // Better for real-time logging
      NODE_ENV: 'production',
      WEB_UI_HOST: '0.0.0.0',
      WEB_UI_PORT: '8080'
    },
    error_file: './logs/err.log',
    out_file: './logs/out.log',
    log_file: './logs/combined.log',
    time: true,
    autorestart: true,
    watch: false,
    max_memory_restart: '1G',
    restart_delay: 3000, // Wait 3s before restart
    max_restarts: 10,    // Limit restart attempts
    min_uptime: '10s'    // Must stay up 10s to be considered successful
  }]
};
