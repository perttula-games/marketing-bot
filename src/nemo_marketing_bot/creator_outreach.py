"""Creator outreach and manual channel setup planning.

The social publishers handle only channels with official posting APIs. This
module covers the parts that still need human execution: creating store/social
pages, finding creators, and giving each creator a clear campaign brief.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from .models import CreatorChannel


DEFAULT_CREATOR_CHANNELS: tuple[CreatorChannel, ...] = (
    "tiktok",
    "youtube",
    "instagram",
    "twitch",
    "reddit",
    "discord",
    "jodel",
    "assembly",
    "lurkit",
    "keymailer",
)

DEFAULT_SETUP_CHANNELS: tuple[CreatorChannel, ...] = (
    "steam",
    "discord",
    "tiktok",
    "youtube",
    "instagram",
    "linkedin",
    "epic",
    "gog",
)

CHANNEL_ALIASES: dict[str, CreatorChannel] = {
    "ig": "instagram",
    "insta": "instagram",
    "reels": "instagram",
    "shorts": "youtube",
    "yt": "youtube",
    "twitter": "reddit",
    "x": "reddit",
    "egs": "epic",
    "epic-games-store": "epic",
    "key-mailer": "keymailer",
}


@dataclass(frozen=True)
class ManualSetupTask:
    channel: CreatorChannel
    priority: int
    title: str
    blocking_inputs: tuple[str, ...]
    checklist: tuple[str, ...]
    done_when: str


@dataclass(frozen=True)
class CreatorTarget:
    channel: CreatorChannel
    priority: int
    target_profile: str
    why: str
    search_queries: tuple[str, ...]
    pitch_angle: str
    deliverables: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    metrics: tuple[str, ...]


@dataclass(frozen=True)
class CreatorPlan:
    game_name: str
    genre: str
    audience: str
    budget: str
    language: str
    store_url: str | None
    discord_url: str | None
    setup_tasks: tuple[ManualSetupTask, ...]
    creator_targets: tuple[CreatorTarget, ...]
    outreach_templates: dict[str, str]


def parse_creator_channels(raw: str | None) -> list[CreatorChannel]:
    """Parse comma-separated channels with a few practical aliases."""
    if not raw:
        return list(DEFAULT_CREATOR_CHANNELS)
    values = [part.strip().lower() for part in raw.split(",") if part.strip()]
    if any(value in {"all", "kaikki"} for value in values):
        return list(DEFAULT_CREATOR_CHANNELS)

    channels: list[CreatorChannel] = []
    known = set(DEFAULT_CREATOR_CHANNELS) | set(DEFAULT_SETUP_CHANNELS)
    for value in values:
        normalized = CHANNEL_ALIASES.get(value, value)
        if normalized not in known:
            choices = ", ".join(sorted(known | set(CHANNEL_ALIASES)))
            raise ValueError(f"Unknown creator channel '{value}'. Choose from: {choices}")
        if normalized not in channels:
            channels.append(normalized)  # type: ignore[arg-type]
    return channels


def build_creator_plan(
    *,
    game_name: str,
    genre: str,
    audience: str,
    budget: str,
    language: str,
    store_url: str | None,
    discord_url: str | None,
    channels: list[CreatorChannel] | None = None,
) -> CreatorPlan:
    wanted = channels or list(DEFAULT_CREATOR_CHANNELS)
    setup = tuple(_build_setup_task(channel) for channel in DEFAULT_SETUP_CHANNELS)
    targets = tuple(
        _build_creator_target(
            channel=channel,
            game_name=game_name,
            genre=genre,
            audience=audience,
            budget=budget,
            language=language,
        )
        for channel in wanted
    )
    return CreatorPlan(
        game_name=game_name,
        genre=genre,
        audience=audience,
        budget=budget,
        language=language,
        store_url=store_url,
        discord_url=discord_url,
        setup_tasks=setup,
        creator_targets=targets,
        outreach_templates=_build_outreach_templates(game_name, genre, store_url, discord_url),
    )


def creator_plan_to_csv(plan: CreatorPlan) -> str:
    """Serialize the creator target matrix for spreadsheets / manual CRM use."""
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=(
            "channel",
            "priority",
            "target_profile",
            "pitch_angle",
            "deliverables",
            "search_queries",
            "metrics",
        ),
    )
    writer.writeheader()
    for target in plan.creator_targets:
        writer.writerow(
            {
                "channel": target.channel,
                "priority": target.priority,
                "target_profile": target.target_profile,
                "pitch_angle": target.pitch_angle,
                "deliverables": " | ".join(target.deliverables),
                "search_queries": " | ".join(target.search_queries),
                "metrics": " | ".join(target.metrics),
            }
        )
    return output.getvalue()


def _build_setup_task(channel: CreatorChannel) -> ManualSetupTask:
    tasks: dict[CreatorChannel, ManualSetupTask] = {
        "steam": ManualSetupTask(
            channel="steam",
            priority=1,
            title="Steam Coming Soon page",
            blocking_inputs=("capsule art", "trailer or teaser", "screenshots", "short description", "tags", "release window"),
            checklist=(
                "Create Steamworks app and Coming Soon page",
                "Add one-sentence player fantasy above the fold",
                "Add UTM-ready store links for creator traffic",
                "Prepare first Steam Event draft for reveal or demo beat",
            ),
            done_when="Public page has clear CTA, tags, media, and creator-specific tracking links.",
        ),
        "discord": ManualSetupTask(
            channel="discord",
            priority=1,
            title="Discord community server",
            blocking_inputs=("server name", "rules", "brand art", "moderator list"),
            checklist=(
                "Create #start-here, #announcements, #general, #feedback, #bugs, #events",
                "Enable Community, Welcome Screen, Onboarding, AutoMod, and Scheduled Events",
                "Add creator/tester roles and private creator support channel",
                "Pin creator brief, build access rules, and feedback format",
            ),
            done_when="A new member can choose language/interests and reach the next event in under one minute.",
        ),
        "tiktok": ManualSetupTask(
            channel="tiktok",
            priority=1,
            title="TikTok account",
            blocking_inputs=("handle", "profile image", "bio", "store or link hub URL"),
            checklist=(
                "Reserve handle and write a bio with one clear next-step CTA",
                "Create first 15 short-form hooks from current gameplay footage",
                "Save reusable caption and hashtag sets",
                "Prepare creator whitelist / Spark Ads notes if paid tests start later",
            ),
            done_when="Profile is live with link, first upload queue, and repeatable hook format.",
        ),
        "youtube": ManualSetupTask(
            channel="youtube",
            priority=1,
            title="YouTube channel",
            blocking_inputs=("handle", "banner", "avatar", "trailer", "default links"),
            checklist=(
                "Set handle, channel art, description, and default site/Discord links",
                "Create Shorts playlist, devlog playlist, and trailer playlist",
                "Prepare thumbnail template for devlogs and feature breakdowns",
                "Upload first Shorts batch from the same footage as TikTok/Reels",
            ),
            done_when="Channel has working links, playlists, and at least one public or scheduled Short.",
        ),
        "instagram": ManualSetupTask(
            channel="instagram",
            priority=1,
            title="Instagram professional account",
            blocking_inputs=("handle", "avatar", "bio", "link hub", "visual templates"),
            checklist=(
                "Switch to professional account and connect Meta Business Suite",
                "Set bio, link, highlight covers, and visual grid rules",
                "Prepare Reels mirror flow from TikTok/Shorts",
                "Create Story templates for polls, countdowns, and creator reposts",
            ),
            done_when="Reels, Stories, highlights, and creator repost flow are ready.",
        ),
        "linkedin": ManualSetupTask(
            channel="linkedin",
            priority=2,
            title="LinkedIn Company Page",
            blocking_inputs=("company details", "logo", "cover image", "website URL"),
            checklist=(
                "Create or refresh Company Page",
                "Add studio positioning, hiring/partnering angle, and website link",
                "Draft first milestone post and founder repost version",
                "List Finnish game industry partners to tag only when relevant",
            ),
            done_when="Company page can publish studio updates and route partner/recruiting interest.",
        ),
        "epic": ManualSetupTask(
            channel="epic",
            priority=3,
            title="Epic Games Store product page",
            blocking_inputs=("confirmed EGS release plan", "store media", "legal/tax setup"),
            checklist=(
                "Confirm EGS release scope before page work",
                "Reuse Steam-ready media with EGS-specific sizing",
                "Add product page to link hub once public",
                "Prepare editorial pitch notes if the game has a clear hook",
            ),
            done_when="EGS page is public or explicitly deferred with owner and date.",
        ),
        "gog": ManualSetupTask(
            channel="gog",
            priority=3,
            title="GOG submission / store page",
            blocking_inputs=("confirmed DRM-free fit", "store assets", "release plan"),
            checklist=(
                "Decide whether the game fits GOG audience and DRM-free expectations",
                "Prepare GOG submission package from Steam assets",
                "Add GOG link only after page is accepted/public",
                "Plan launch/sale announcement copy if accepted",
            ),
            done_when="GOG is either accepted into launch plan or intentionally parked.",
        ),
    }
    return tasks[channel]


def _build_creator_target(
    *,
    channel: CreatorChannel,
    game_name: str,
    genre: str,
    audience: str,
    budget: str,
    language: str,
) -> CreatorTarget:
    common_metrics = ("tracked link clicks", "demo installs or devlog reads", "coverage quality", "creator response rate")
    targets: dict[CreatorChannel, CreatorTarget] = {
        "tiktok": CreatorTarget(
            channel="tiktok",
            priority=1,
            target_profile=f"Micro and mid-size short-form creators who already post {genre}, indie discoveries, or gameplay reactions for {audience}.",
            why="Fastest early discovery loop and easiest place to test hooks before spending media budget.",
            search_queries=(
                f'TikTok search: "{genre} indie game"',
                'TikTok hashtags: #indiegame #gamedev #steamnextfest #pcgaming',
                f'Google: site:tiktok.com "{genre}" "indie game" creator',
            ),
            pitch_angle=f"Give them one surprising {game_name} mechanic they can understand in the first second.",
            deliverables=("1-2 organic videos", "raw performance stats after 72 hours", "permission request for whitelisting if performance is strong"),
            acceptance_criteria=("recent gaming posts", "real comments, not empty likes", "clear disclosure habits", "fits the game's tone"),
            metrics=common_metrics + ("3s hold rate", "saves/shares"),
        ),
        "youtube": CreatorTarget(
            channel="youtube",
            priority=1,
            target_profile=f"YouTube Shorts creators, indie discovery channels, and small reviewers with visible {genre} interest.",
            why="Combines Shorts discovery with long-tail searchable coverage.",
            search_queries=(
                f'YouTube search: "new {genre} indie game"',
                f'YouTube search: "Steam Next Fest {genre}"',
                f'Google: site:youtube.com "{genre}" "indie game" "demo"',
            ),
            pitch_angle="Offer a playable demo/key plus a clean 30-second hook, not a generic press release.",
            deliverables=("1 Short or community post", "optional 8-15 minute demo impressions video", "link in description with UTM"),
            acceptance_criteria=("audience comments ask about games", "creator covers demos or indies", "thumbnails/titles are not misleading"),
            metrics=common_metrics + ("average view duration", "description CTR"),
        ),
        "instagram": CreatorTarget(
            channel="instagram",
            priority=1,
            target_profile="Reels creators, visual indie game pages, meme pages with gaming fit, and artists who can amplify striking clips or key art.",
            why="Good visual showroom and a strong mirror for TikTok/Reels footage.",
            search_queries=(
                'Instagram hashtags: #indiegames #gamedev #pcgaming #indiedev',
                f'Instagram search: "{genre}" "indie game"',
                'Meta Creator Marketplace filters: gaming, Finland/Nordics, English-speaking',
            ),
            pitch_angle="Lead with the most visually readable clip and ask for a Reel, not a static ad.",
            deliverables=("1 Reel", "3-5 Story frames with link sticker", "permission to repost to studio account"),
            acceptance_criteria=("Reels outperform static posts", "audience fits game age rating", "brand-safe comments"),
            metrics=common_metrics + ("profile visits", "story link taps"),
        ),
        "twitch": CreatorTarget(
            channel="twitch",
            priority=2,
            target_profile=f"Small to mid-size streamers who play {genre}, demos, Steam festivals, co-op challenges, or Finnish/Nordic indie games.",
            why="Best for live reactions, demo feedback, and community proof around campaign beats.",
            search_queries=(
                f'Twitch category/search: "{genre}" and "indie"',
                f'YouTube/Twitch cross-search: "{genre}" "first impressions"',
                'Lurkit/Keymailer filters: Twitch, PC, indie, English/Finnish',
            ),
            pitch_angle="Invite them to a short hands-on demo with developer availability for chat questions.",
            deliverables=("30-90 minute demo stream", "VOD/highlight permission", "Discord invite CTA during stream"),
            acceptance_criteria=("chat is active", "streamer has played similar games", "disclosure and key policy are clear"),
            metrics=common_metrics + ("watch time", "chat sentiment", "Discord joins"),
        ),
        "reddit": CreatorTarget(
            channel="reddit",
            priority=2,
            target_profile="Subreddit-native posters, moderators where appropriate, and creators who can share transparent dev material without astroturfing.",
            why="High-intent feedback and word-of-mouth when the post fits community rules.",
            search_queries=(
                f'Reddit search: "{genre}" "indie" "feedback"',
                'Subreddits to audit: r/IndieGaming, r/gamedev, genre-specific subreddits',
                f'Google: site:reddit.com/r "{genre}" "Steam" "demo"',
            ),
            pitch_angle="Ask one honest question about a GIF or mechanic; do not lead with a campaign ask.",
            deliverables=("1 feedback post where rules allow", "comment follow-up by developer", "AMA only after visible interest"),
            acceptance_criteria=("community rules permit self-promo", "poster is transparent", "thread invites feedback"),
            metrics=common_metrics + ("comment quality", "upvote ratio"),
        ),
        "discord": CreatorTarget(
            channel="discord",
            priority=1,
            target_profile="Early community ambassadors, testers, moderators, and creators who can bring a small but active audience into the server.",
            why="Turns one-off creator traffic into retained community members.",
            search_queries=(
                'Current followers who reply/comment repeatedly',
                'Creators who ask for demo access or feedback channels',
                f'Finnish/Nordic game dev Discords and {genre} community servers',
            ),
            pitch_angle="Offer a creator/tester role, early build notes, and a clear weekly feedback rhythm.",
            deliverables=("creator role", "one scheduled community event", "feedback thread or office-hours participation"),
            acceptance_criteria=("constructive tone", "no spammy invite trading", "can follow embargo/build rules"),
            metrics=("joins/week", "7-day retention", "event RSVPs", "feedback items"),
        ),
        "jodel": CreatorTarget(
            channel="jodel",
            priority=3,
            target_profile="Local campus/community activation partners in Finnish cities; treat as burst support, not a persistent creator channel.",
            why="Useful for Finnish local spikes around demo, event, Assembly, or recruiting moments.",
            search_queries=(
                'Jodel Business / local campaign quote request',
                'Campus gaming clubs in Helsinki, Tampere, Jyväskylä, Oulu, Turku',
                'Local student associations with gaming or tech audiences',
            ),
            pitch_angle="Make it local: Finnish project, specific city/event, short ask for honest demo feedback.",
            deliverables=("1-2 week local burst", "city-specific copy variants", "tracked local link"),
            acceptance_criteria=("clear local relevance", "no fake grassroots posting", "timed to real beat"),
            metrics=("local link clicks", "Discord joins", "demo feedback", "cost per visit"),
        ),
        "assembly": CreatorTarget(
            channel="assembly",
            priority=2,
            target_profile="Assembly showcase contacts, event streamers, and Finnish gaming creators attending or covering the event.",
            why="Best Finnish visibility spike when there is a playable demo or showcase story.",
            search_queries=(
                'Assembly Indie Showcase contacts',
                'Assembly streamers gaming indie showcase Finland',
                'Finnish gaming creators attending Assembly',
            ),
            pitch_angle="Frame the game as a playable Finnish indie demo with a clear live moment.",
            deliverables=("showcase application", "demo booth/stream slot", "creator hands-on schedule"),
            acceptance_criteria=("real event fit", "demo is stable", "staff can capture follow-up content"),
            metrics=("booth plays", "creator mentions", "demo installs", "press/partner leads"),
        ),
        "lurkit": CreatorTarget(
            channel="lurkit",
            priority=1,
            target_profile="Lurkit creator program candidates filtered by PC, indie, genre fit, language, and engagement quality.",
            why="Structured creator CRM and key-seeding path without building a spreadsheet from zero.",
            search_queries=(
                f'Lurkit filters: PC, {genre}, indie, {language}',
                'Lurkit organic key campaign setup',
                'Lurkit paid quests only after organic signal',
            ),
            pitch_angle="Open an always-on creator program, then add paid quests only for demo/launch beats.",
            deliverables=("creator program page", "key-seeding campaign", "demo/launch campaign flight"),
            acceptance_criteria=("verified creators", "genre fit", "clear deliverable terms", f"budget tier: {budget}"),
            metrics=common_metrics + ("key redemption", "deliverable completion"),
        ),
        "keymailer": CreatorTarget(
            channel="keymailer",
            priority=1,
            target_profile="Keymailer creator and press requests with strong fit, visible previous coverage, and clean contact history.",
            why="Efficient key distribution and press/creator request management before demo or launch.",
            search_queries=(
                f'Keymailer campaign filters: PC, {genre}, indie, English/Finnish',
                'Keymailer press list: Finnish games media and indie reviewers',
                'Keymailer embargo key campaign for demo beat',
            ),
            pitch_angle="Give creators a frictionless key request path plus a compact press kit.",
            deliverables=("key request campaign", "press kit attached", "embargo notes if needed"),
            acceptance_criteria=("previous relevant coverage", "no key farming signals", "clear platform ownership"),
            metrics=common_metrics + ("key requests approved", "coverage per key"),
        ),
        "linkedin": CreatorTarget(
            channel="linkedin",
            priority=3,
            target_profile="Game industry operators, Finnish studio founders, recruiters, investors, publisher scouts, and partner voices.",
            why="Not a consumer discovery engine, but useful for legitimacy, hiring, and partnerships.",
            search_queries=(
                'LinkedIn search: Finnish games industry indie studio publisher',
                'LinkedIn groups/events: IGDA Finland, Neogames, Nordic Game',
                f'LinkedIn posts: "{genre}" "game dev" "Finland"',
            ),
            pitch_angle="Ask for a thoughtful repost or intro only when there is a real milestone.",
            deliverables=("founder repost", "partner intro", "milestone amplification"),
            acceptance_criteria=("relevant professional audience", "no consumer-conversion expectation", "clear business reason"),
            metrics=("profile visits", "inbound leads", "reposts", "partner conversations"),
        ),
    }
    if channel not in targets:
        return CreatorTarget(
            channel=channel,
            priority=3,
            target_profile=f"Manual partner channel for {game_name}; use only if it has confirmed release or campaign fit.",
            why="This channel supports distribution rather than creator discovery.",
            search_queries=(f"{channel} developer submission", f"{channel} indie game marketing"),
            pitch_angle="Confirm platform fit before spending outreach time.",
            deliverables=("store/platform page", "launch announcement", "tracked link"),
            acceptance_criteria=("confirmed release plan", "assets ready", "owner assigned"),
            metrics=("page visits", "demo installs", "store conversion"),
        )
    return targets[channel]


def _build_outreach_templates(
    game_name: str,
    genre: str,
    store_url: str | None,
    discord_url: str | None,
) -> dict[str, str]:
    store = store_url or "[Steam / store URL]"
    discord = discord_url or "[Discord invite]"
    return {
        "creator_dm_en": (
            f"Hey [name] - I am working on {game_name}, a {genre} game, and your recent "
            "coverage felt like a strong fit. The fastest hook is [one mechanic in one sentence].\n\n"
            f"Would you be open to trying a demo/key for a short video or stream? Store: {store}\n"
            f"Creator notes / Discord: {discord}\n\n"
            "No pressure on coverage; honest feedback is useful either way."
        ),
        "creator_dm_fi": (
            f"Moi [nimi] - teen peliä {game_name}, joka on {genre}-henkinen projekti. "
            "Sun viimeaikainen pelisisältö osuu tosi hyvin siihen yleisöön, jolle tätä rakennetaan.\n\n"
            "Kiinnostaisiko testata demo/key ja tehdä siitä lyhyt video, streami tai rehellinen ensifiilis? "
            f"Store: {store}\nDiscord/creator-notes: {discord}\n\n"
            "Ei pakkoa tehdä coveragea, palaute on jo itsessään arvokasta."
        ),
        "follow_up": (
            "Hey [name] - quick follow-up on the demo/key offer. The useful angle for your audience would be "
            "[specific mechanic/challenge], and we can provide clean clips, screenshots, and a short fact sheet. "
            "Happy to leave it if the timing is not right."
        ),
        "creator_brief": (
            f"Creator brief for {game_name}\n"
            f"Genre: {genre}\n"
            "Core hook: [one sentence player fantasy]\n"
            "Allowed footage: [yes/no + embargo date]\n"
            "Best beats to show: [3 mechanics or moments]\n"
            "CTA: read the latest devlog or join Discord, one CTA per post\n"
            f"Store link: {store}\n"
            f"Discord/support: {discord}\n"
            "Disclosure: mark paid/sponsored content clearly when applicable."
        ),
    }