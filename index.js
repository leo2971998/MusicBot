require('dotenv').config();
const {
    Client,
    GatewayIntentBits,
    PermissionsBitField,
    ChannelType,
    ActionRowBuilder,
    ButtonBuilder,
    ButtonStyle,
    EmbedBuilder,
} = require('discord.js');
const { Player, QueryType } = require('discord-player');
const { Downloader } = require('@discord-player/downloader');
const fs = require('fs');

const client = new Client({
    intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildVoiceStates,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.MessageContent,
    ],
});

// Initialize the player
const player = new Player(client);

// Instantiate and register the downloader
const downloader = new Downloader();
player.extractors.register(downloader);

// Optional: Log registered extractors
console.log('Registered Extractors:', player.extractors.extractors.map(ext => ext.constructor.name));

const configFilePath = './config.json';

function saveConfig(config) {
    fs.writeFileSync(configFilePath, JSON.stringify(config, null, 4));
}

function loadConfig() {
    if (!fs.existsSync(configFilePath)) {
        return { guilds: {} };
    }
    return JSON.parse(fs.readFileSync(configFilePath));
}

const config = loadConfig();

client.once('ready', async () => {
    console.log('Bot is online!');

    for (const guildId in config.guilds) {
        const { channelId, stableMessageId } = config.guilds[guildId];
        try {
            const guild = await client.guilds.fetch(guildId);

            // Attempt to fetch the channel
            let channel;
            try {
                channel = await guild.channels.fetch(channelId);
            } catch (channelError) {
                console.error(`Channel with ID ${channelId} not found in guild ${guildId}. Removing guild from config.`);
                delete config.guilds[guildId];
                saveConfig(config);
                continue; // Skip to the next guild
            }

            // Attempt to fetch the message
            let message;
            try {
                message = await channel.messages.fetch(stableMessageId);
            } catch (messageError) {
                console.error(`Message with ID ${stableMessageId} not found in channel ${channelId}. Removing guild from config.`);
                delete config.guilds[guildId];
                saveConfig(config);
                continue; // Skip to the next guild
            }

            config.guilds[guildId].stableMessage = message;
            console.log(`Fetched stable message for guild ${guildId}`);
        } catch (error) {
            console.error(`Failed to fetch data for guild ${guildId}:`, error);
        }
    }
});

async function updateStableMessage(guildId, queue) {
    const guildConfig = config.guilds[guildId];
    if (!guildConfig || !guildConfig.stableMessage) {
        console.log(`No stable message found for guild ${guildId}`);
        return;
    }

    const stableMessage = guildConfig.stableMessage;
    const currentTrack = queue.currentTrack;
    if (!currentTrack) {
        await stableMessage.edit({
            content: 'No music is currently playing.',
            embeds: [],
            components: [],
        });
        console.log(`Updated stable message: No music is currently playing.`);
        return;
    }

    const nowPlayingEmbed = new EmbedBuilder()
        .setTitle('🎶 Now Playing')
        .setDescription(`**[${currentTrack.title}](${currentTrack.url})**`)
        .setThumbnail(currentTrack.thumbnail)
        .setFooter({ text: 'Use the buttons below to control playback.' })
        .setColor(0x1db954);

    const tracks = queue.tracks.toArray();

    const queueButtons = [];
    let currentRow = new ActionRowBuilder();

    tracks.forEach((track, index) => {
        if (currentRow.components.length === 5) {
            queueButtons.push(currentRow);
            currentRow = new ActionRowBuilder();
        }
        currentRow.addComponents(
            new ButtonBuilder()
                .setCustomId(`remove_${index}`)
                .setLabel(`❌ Remove ${index + 1}`)
                .setStyle(ButtonStyle.Primary)
        );
    });

    if (currentRow.components.length > 0) {
        queueButtons.push(currentRow);
    }

    const controlButtons = new ActionRowBuilder().addComponents(
        new ButtonBuilder()
            .setCustomId('pause')
            .setLabel('⏸️ Pause')
            .setStyle(ButtonStyle.Primary),
        new ButtonBuilder()
            .setCustomId('resume')
            .setLabel('▶️ Play')
            .setStyle(ButtonStyle.Primary),
        new ButtonBuilder()
            .setCustomId('skip')
            .setLabel('⏭️ Skip')
            .setStyle(ButtonStyle.Primary),
        new ButtonBuilder()
            .setCustomId('stop')
            .setLabel('⏹️ Stop')
            .setStyle(ButtonStyle.Primary)
    );

    const queueEmbed = new EmbedBuilder()
        .setTitle('📜 Current Queue')
        .setDescription(
            tracks
                .map((track, index) => `${index + 1}. **[${track.title}](${track.url})**`)
                .join('\n') || 'No more songs in the queue.'
        )
        .setFooter({ text: `Total songs in queue: ${tracks.length}` });

    await stableMessage.edit({
        content: null,
        embeds: [nowPlayingEmbed, queueEmbed],
        components: [controlButtons, ...queueButtons],
    });
    console.log(`Updated stable message for guild ${guildId}`);
}

async function clearMessages(channel, guildId) {
    const guildConfig = config.guilds[guildId];
    if (!guildConfig || !guildConfig.stableMessage) return;

    const stableMessage = guildConfig.stableMessage;
    const messages = await channel.messages.fetch({ limit: 100 });
    const messagesToDelete = messages.filter((msg) => msg.id !== stableMessage.id);
    await channel.bulkDelete(messagesToDelete);
    console.log(`Cleared messages in channel ${channel.id} except for stable message`);
}

client.on('messageCreate', async (message) => {
    if (message.author.bot || !message.guild) return;

    const guildId = message.guild.id;

    if (message.content.startsWith('!setup')) {
        let channel = message.guild.channels.cache.find((ch) => ch.name === 'leo-song-requests');

        if (!channel) {
            try {
                channel = await message.guild.channels.create({
                    name: 'leo-song-requests',
                    type: ChannelType.GuildText,
                    permissionOverwrites: [
                        {
                            id: message.guild.id,
                            allow: [
                                PermissionsBitField.Flags.ViewChannel,
                                PermissionsBitField.Flags.SendMessages,
                                PermissionsBitField.Flags.ReadMessageHistory,
                            ],
                        },
                    ],
                });
                console.log(`Created channel leo-song-requests in guild ${guildId}`);
            } catch (error) {
                console.error(error);
                return message.channel.send('Failed to create the music commands channel.');
            }
        }

        try {
            const setupMessage = await channel.send('Setting up the music bot UI...');
            config.guilds[guildId] = {
                channelId: channel.id,
                stableMessageId: setupMessage.id,
                stableMessage: setupMessage, // Ensuring the message is also saved directly
            };
            saveConfig(config);
            message.channel.send('Music commands channel setup complete.');
            console.log(`Setup complete for guild ${guildId}`);

            // Update the stable message immediately
            await updateStableMessage(guildId, { currentTrack: null, tracks: [] });
        } catch (error) {
            console.error(error);
            message.channel.send('Failed to set up the music commands channel.');
        }
    }

    if (message.channel.name === 'leo-song-requests') {
        if (message.content.startsWith('play')) {
            const args = message.content.split(' ').slice(1);
            const query = args.join(' ');

            if (!query) {
                return message.channel.send('Please provide a song name or YouTube link.');
            }

            // Check if the user is in a voice channel
            if (!message.member.voice.channel) {
                return message.channel.send('You need to be in a voice channel to play music!');
            }

            try {
                const searchResult = await player.search(query, {
                    requestedBy: message.author,
                    searchEngine: QueryType.AUTO,
                });

                if (!searchResult || !searchResult.tracks.length) {
                    return message.channel.send('No results found!');
                }

                let queue = player.nodes.get(message.guild.id);
                if (!queue) {
                    queue = await player.nodes.create(message.guild, {
                        metadata: {
                            channel: message.channel,
                        },
                        selfDeaf: true, // Ensure the bot is deafened to prevent echo
                    });

                    try {
                        if (!queue.connection) {
                            await queue.connect(message.member.voice.channel);
                        }
                    } catch (error) {
                        console.error('Error joining voice channel:', error);
                        player.nodes.delete(message.guild.id);
                        return message.channel.send('Could not join your voice channel!');
                    }
                }

                queue.addTrack(searchResult.tracks[0]);
                message.channel.send(`Added **${searchResult.tracks[0].title}** to the queue.`);
                console.log('Track added to the queue.');

                // Update the stable message
                updateStableMessage(guildId, queue);

                // Clear all messages in the channel except the stable message
                clearMessages(message.channel, guildId);
            } catch (error) {
                console.error('Error playing track:', error);
                message.channel.send('An error occurred while trying to play the track.');
            }
        }
    }
});

client.on('interactionCreate', async (interaction) => {
    if (!interaction.isButton()) return;

    const queue = player.nodes.get(interaction.guildId);
    if (!queue)
        return interaction.reply({
            content: 'No music is being played!',
            ephemeral: true,
        });

    try {
        const guildId = interaction.guildId;

        if (interaction.customId === 'pause') {
            queue.node.setPaused(true);
            interaction.reply({ content: 'Paused music!', ephemeral: true });

            // Update the stable message
            updateStableMessage(guildId, queue);
        } else if (interaction.customId === 'resume') {
            queue.node.setPaused(false);
            interaction.reply({ content: 'Resumed 
