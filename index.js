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
} = require("discord.js");
const { Player, QueryType } = require("discord-player");
const {
    YouTubeExtractor,
    SpotifyExtractor,
} = require("@discord-player/extractor");
const fs = require("fs");

const client = new Client({
    intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildVoiceStates,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.MessageContent,
    ],
});

const player = new Player(client);

player.extractors.register(YouTubeExtractor, {});
player.extractors.register(SpotifyExtractor, {});

let stableMessage = null; // Store the stable message object

const configFilePath = "./config.json";

function saveConfig(config) {
    fs.writeFileSync(configFilePath, JSON.stringify(config, null, 4));
}

function loadConfig() {
    if (!fs.existsSync(configFilePath)) {
        return {};
    }
    return JSON.parse(fs.readFileSync(configFilePath));
}

const config = loadConfig();

client.once("ready", async () => {
    console.log("Bot is online!");

    if (config.stableMessageId && config.channelId) {
        try {
            const channel = await client.channels.fetch(config.channelId);
            stableMessage = await channel.messages.fetch(
                config.stableMessageId,
            );
        } catch (error) {
            console.error("Failed to fetch the stable message:", error);
        }
    }
});

async function updateStableMessage(queue) {
    if (!stableMessage) return;

    const currentTrack = queue.currentTrack;
    if (!currentTrack) {
        await stableMessage.edit({
            content: "No music is currently playing.",
            embeds: [],
            components: [],
        });
        return;
    }

    const nowPlayingEmbed = new EmbedBuilder()
        .setTitle("🎶 Now Playing")
        .setDescription(`**[${currentTrack.title}](${currentTrack.url})**`)
        .setThumbnail(currentTrack.thumbnail)
        .setFooter({ text: "Use the buttons below to control playback." })
        .setColor(0x1db954);

    const tracks = queue.tracks.toArray(); // Convert collection to array

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
                .setLabel(`❌ Remove number ${index + 1} song`)
                .setStyle(ButtonStyle.Primary),
        );
    });

    if (currentRow.components.length > 0) {
        queueButtons.push(currentRow);
    }

    const controlButtons = new ActionRowBuilder().addComponents(
        new ButtonBuilder()
            .setCustomId("pause")
            .setLabel("⏸️ Pause")
            .setStyle(ButtonStyle.Primary),
        new ButtonBuilder()
            .setCustomId("resume")
            .setLabel("▶️ Play")
            .setStyle(ButtonStyle.Primary),
        new ButtonBuilder()
            .setCustomId("skip")
            .setLabel("⏭️ Skip")
            .setStyle(ButtonStyle.Primary),
        new ButtonBuilder()
            .setCustomId("stop")
            .setLabel("⏹️ Stop")
            .setStyle(ButtonStyle.Primary),
    );

    const queueEmbed = new EmbedBuilder()
        .setTitle("📜 Current Queue")
        .setDescription(
            tracks
                .map(
                    (track, index) =>
                        `${index + 1}. **[${track.title}](${track.url})**`,
                )
                .join("\n") || "No more songs in the queue.",
        )
        .setFooter({ text: `Total songs in queue: ${tracks.length}` });

    await stableMessage.edit({
        content: null,
        embeds: [nowPlayingEmbed, queueEmbed],
        components: [controlButtons, ...queueButtons],
    });
}

async function clearMessages(channel) {
    if (!stableMessage) return; // Check if stableMessage is null
    const messages = await channel.messages.fetch({ limit: 100 });
    const messagesToDelete = messages.filter(
        (msg) => msg.id !== stableMessage.id,
    );
    await channel.bulkDelete(messagesToDelete);
}

client.on("messageCreate", async (message) => {
    if (message.author.bot || !message.guild) return;

    if (message.content.startsWith("!setup")) {
        const guild = message.guild;
        let channel = guild.channels.cache.find(
            (ch) => ch.name === "leo-song-requests",
        );

        if (!channel) {
            try {
                channel = await guild.channels.create({
                    name: "leo-song-requests",
                    type: ChannelType.GuildText,
                    permissionOverwrites: [
                        {
                            id: guild.id,
                            allow: [
                                PermissionsBitField.Flags.ViewChannel,
                                PermissionsBitField.Flags.SendMessages,
                                PermissionsBitField.Flags.ReadMessageHistory,
                            ],
                        },
                    ],
                });

                stableMessage = await channel.send(
                    "Setting up the music bot UI...",
                );
                config.channelId = channel.id;
                config.stableMessageId = stableMessage.id;
                saveConfig(config);
                channel.send(
                    "This is your new music commands channel. Use `play <song name>` or `play <YouTube link>` to play music.",
                );
            } catch (error) {
                console.error(error);
                message.channel.send(
                    "Failed to create the music commands channel.",
                );
            }
        } else {
            stableMessage = await channel.send(
                "Setting up the music bot UI...",
            );
            config.channelId = channel.id;
            config.stableMessageId = stableMessage.id;
            saveConfig(config);
            channel.send("Music commands channel already exists.");
        }
    }

    if (message.channel.name === "leo-song-requests") {
        if (message.content.startsWith("play")) {
            const args = message.content.split(" ").slice(1);
            const query = args.join(" ");

            if (!query) {
                return message.channel.send(
                    "Please provide a song name or YouTube link.",
                );
            }

            try {
                const searchResult = await player.search(query, {
                    requestedBy: message.author,
                    searchEngine: QueryType.AUTO,
                });

                if (!searchResult || !searchResult.tracks.length) {
                    return message.channel.send("No results found!");
                }

                let queue = player.nodes.get(message.guild.id);
                if (!queue) {
                    queue = await player.nodes.create(message.guild, {
                        metadata: {
                            channel: message.channel,
                        },
                    });

                    try {
                        if (!queue.connection)
                            await queue.connect(message.member.voice.channel);
                    } catch {
                        player.nodes.delete(message.guild.id);
                        return message.channel.send(
                            "Could not join your voice channel!",
                        );
                    }

                    queue.addTrack(searchResult.tracks[0]);
                    await queue.node.play();

                    updateStableMessage(queue);
                } else {
                    queue.addTrack(searchResult.tracks[0]);
                    message.channel.send(
                        `Added **${searchResult.tracks[0].title}** to the queue.`,
                    );

                    // Update the stable message
                    updateStableMessage(queue);
                }

                // Clear all messages in the channel except the stable message
                clearMessages(message.channel);
            } catch (error) {
                console.error(error);
                message.channel.send(
                    "An error occurred while trying to play the track.",
                );
            }
        }
    }
});

client.on("interactionCreate", async (interaction) => {
    if (!interaction.isButton()) return;

    const queue = player.nodes.get(interaction.guildId);
    if (!queue)
        return interaction.reply({
            content: "No music is being played!",
            ephemeral: true,
        });

    try {
        if (interaction.customId === "pause") {
            queue.node.setPaused(true);
            interaction.reply({ content: "Paused music!", ephemeral: true });

            // Update the button to "Resume"
            updateStableMessage(queue);
        } else if (interaction.customId === "resume") {
            queue.node.setPaused(false);
            interaction.reply({ content: "Resumed music!", ephemeral: true });

            // Update the button to "Pause"
            updateStableMessage(queue);
        } else if (interaction.customId === "skip") {
            queue.node.skip();
            interaction.reply({
                content: "Skipped to next song!",
                ephemeral: true,
            });

            // Update the stable message
            updateStableMessage(queue);
        } else if (interaction.customId === "stop") {
            queue.node.stop();
            interaction.reply({
                content: "Stopped the music!",
                ephemeral: true,
            });

            // Update the stable message
            updateStableMessage(queue);
        } else if (interaction.customId.startsWith("remove_")) {
            const index = parseInt(interaction.customId.split("_")[1], 10);
            const tracks = queue.tracks.toArray(); // Convert collection to array
            if (!isNaN(index) && tracks[index]) {
                const removedTrack = tracks.splice(index, 1)[0];
                queue.tracks.clear();
                tracks.forEach((track) => queue.addTrack(track));
                interaction.reply({
                    content: `Removed **${removedTrack.title}** from the queue.`,
                    ephemeral: true,
                });

                // Update the stable message
                updateStableMessage(queue);
            } else {
                interaction.reply({
                    content: "Invalid track index.",
                    ephemeral: true,
                });
            }
        }
    } catch (error) {
        console.error(error);
        interaction.reply({
            content: "An error occurred while processing your interaction.",
            ephemeral: true,
        });
    }
});
player.events.on("playerStart", (queue, track) => {
    updateStableMessage(queue);
});

client.login(process.env.DISCORD_TOKEN);
