"""Organic follower growth planning for manual social accounts."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Literal

GrowthChannel = Literal["bluesky", "x"]


@dataclass(frozen=True)
class GrowthAction:
    day: int
    channel: GrowthChannel
    action: str
    goal: str
    limit: str
    evidence: str


@dataclass(frozen=True)
class GrowthTarget:
    channel: GrowthChannel
    target_profile: str
    search_queries: tuple[str, ...]
    follow_criteria: tuple[str, ...]
    engagement_openers: tuple[str, ...]
    avoid: tuple[str, ...]


@dataclass(frozen=True)
class GrowthPlan:
    game_name: str
    positioning: str
    audience: str
    channels: tuple[GrowthChannel, ...]
    bio_cta: str
    actions: tuple[GrowthAction, ...]
    targets: tuple[GrowthTarget, ...]
    kpi_columns: tuple[str, ...]


CHANNEL_ALIASES: dict[str, GrowthChannel] = {
    "bsky": "bluesky",
    "blue": "bluesky",
    "bluesky": "bluesky",
    "twitter": "x",
    "x": "x",
}

DEFAULT_CHANNELS: tuple[GrowthChannel, ...] = ("bluesky", "x")


def parse_growth_channels(raw: str | None) -> list[GrowthChannel]:
    if not raw or raw.strip().lower() in {"all", "both"}:
        return list(DEFAULT_CHANNELS)

    channels: list[GrowthChannel] = []
    for part in raw.split(","):
        value = part.strip().lower()
        if not value:
            continue
        channel = CHANNEL_ALIASES.get(value)
        if channel is None:
            choices = ", ".join(sorted(CHANNEL_ALIASES))
            raise ValueError(f"Unknown growth channel '{value}'. Choose from: {choices}")
        if channel not in channels:
            channels.append(channel)
    return channels or list(DEFAULT_CHANNELS)


def build_growth_plan(
    *,
    game_name: str = "Kalma",
    positioning: str = "PC first-person survival horror",
    audience: str = "PC horror players and indie horror developers",
    channels: list[GrowthChannel] | None = None,
    daily_follow_limit: int = 15,
    daily_like_limit: int = 12,
    daily_reply_limit: int = 10,
) -> GrowthPlan:
    """Build a safe organic follower growth plan.

    The plan intentionally produces manual actions. It does not automate
    follows, likes, reposts, DMs, or replies.
    """

    selected = tuple(channels or DEFAULT_CHANNELS)
    if daily_follow_limit < 0 or daily_like_limit < 0 or daily_reply_limit < 0:
        raise ValueError("daily limits must be zero or greater")

    bio_cta = (
        f"Building {game_name}, a {positioning}. "
        "Here to connect with horror players, indie devs, and people who like slow dread."
    )

    actions: list[GrowthAction] = []
    for channel in selected:
        actions.extend(
            [
                GrowthAction(
                    day=1,
                    channel=channel,
                    action="Find 3-5 relevant feeds, lists, hashtags, or search columns.",
                    goal="Route effort toward people who already care about indie horror.",
                    limit="Research only; no follows yet.",
                    evidence="Fedica emphasizes matching feeds/interests and genuine community fit.",
                ),
                GrowthAction(
                    day=2,
                    channel=channel,
                    action=f"Follow up to {daily_follow_limit} clearly relevant accounts.",
                    goal="Seed the account graph with likely horror players, devs, and small creators.",
                    limit="Only follow accounts with recent relevant posts and no spam signals.",
                    evidence="Following relevant people first can increase visibility through the social graph.",
                ),
                GrowthAction(
                    day=3,
                    channel=channel,
                    action=(
                        f"Leave up to {daily_like_limit} relevant likes and write up to "
                        f"{daily_reply_limit} thoughtful replies from the account."
                    ),
                    goal="Create visible, human interactions before asking for follows.",
                    limit="No reposts, no generic praise, no copy-pasted replies, no sales CTA in replies.",
                    evidence="The strongest growth advice is relevant replies, selective likes, and relationship building.",
                ),
                GrowthAction(
                    day=4,
                    channel=channel,
                    action="Post a visual Kalma atmosphere beat and reply to every serious response.",
                    goal="Give profile visitors a reason to follow after the interaction pass.",
                    limit="Use actual Kalma visuals only; do not imply demo, Steam page, or release date.",
                    evidence="Consistent posting plus engagement keeps the account visible without spamming.",
                ),
                GrowthAction(
                    day=5,
                    channel=channel,
                    action="Review followers gained, engagement rate, follow-back quality, and replies.",
                    goal="Keep the accounts that engage and refine target pools for next week.",
                    limit="Do not unfollow people as a growth tactic; prune only obvious spam manually.",
                    evidence="Track ratios, not only raw follower count, to avoid low-quality growth.",
                ),
            ]
        )

    targets = tuple(_build_target(channel, game_name, positioning, audience) for channel in selected)

    return GrowthPlan(
        game_name=game_name,
        positioning=positioning,
        audience=audience,
        channels=selected,
        bio_cta=bio_cta,
        actions=tuple(actions),
        targets=targets,
        kpi_columns=(
            "date",
            "channel",
            "followers_before",
            "followers_after",
            "relevant_follows_made",
            "relevant_likes",
            "thoughtful_replies",
            "posts_published",
            "profile_visits",
            "link_clicks",
            "new_followers",
            "engagement_rate",
            "follow_rate",
            "notes",
        ),
    )


def growth_plan_to_markdown(plan: GrowthPlan) -> str:
    lines: list[str] = [
        f"# {plan.game_name} Organic Follower Growth Plan",
        "",
        f"- Positioning: {plan.positioning}",
        f"- Audience: {plan.audience}",
        f"- Channels: {', '.join(plan.channels)}",
        f"- Bio CTA: {plan.bio_cta}",
        "",
        "## Safety Rules",
        "",
        "- Manual actions only: no automated following, liking, reposting, DMs, or replies.",
        "- Never repost or quote-post from this account.",
        "- Follow only accounts with recent, relevant horror/game-dev/indie-game activity.",
        "- Do not use follow-unfollow tactics.",
        "- Do not promise a demo, Steam page, release date, price, or mechanics that are not confirmed.",
        "- Keep replies specific to the other person's post; do not paste the same reply repeatedly.",
        "",
        "## Daily Actions",
        "",
        "| Day | Channel | Action | Goal | Limit | Evidence |",
        "| --- | --- | --- | --- | --- | --- |",
    ]

    for action in plan.actions:
        lines.append(
            "| "
            f"Day {action.day} | {action.channel} | {action.action} | {action.goal} | "
            f"{action.limit} | {action.evidence} |"
        )

    lines.extend(["", "## Target Pools", ""])
    for target in plan.targets:
        lines.extend(
            [
                f"### {target.channel}",
                "",
                f"- Who: {target.target_profile}",
                f"- Search: {'; '.join(target.search_queries)}",
                f"- Follow criteria: {'; '.join(target.follow_criteria)}",
                f"- Reply openers: {'; '.join(target.engagement_openers)}",
                f"- Avoid: {'; '.join(target.avoid)}",
                "",
            ]
        )

    lines.extend(
        [
            "## KPI Columns",
            "",
            ", ".join(plan.kpi_columns),
            "",
        ]
    )
    return "\n".join(lines)


def growth_plan_to_csv(plan: GrowthPlan) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["day", "channel", "action", "goal", "limit", "evidence"])
    for action in plan.actions:
        writer.writerow([action.day, action.channel, action.action, action.goal, action.limit, action.evidence])
    return output.getvalue()


def _build_target(
    channel: GrowthChannel,
    game_name: str,
    positioning: str,
    audience: str,
) -> GrowthTarget:
    if channel == "bluesky":
        return GrowthTarget(
            channel=channel,
            target_profile=(
                f"{audience}; indie horror devs; small streamers; screenshot-sharing game-dev accounts; "
                "people active in Bluesky feeds around indie games, horror, Unreal Engine, and Finnish games."
            ),
            search_queries=(
                '"indie horror"',
                '"survival horror"',
                '"Unreal Engine" "horror"',
                '"Finnish game dev"',
                f'"{game_name}"',
                "blueskyfeeds.com indie games horror",
                "goodfeeds.co game dev horror",
            ),
            follow_criteria=(
                "posted or replied within the last 30 days",
                f"mentions horror games, indie games, Unreal Engine, or {positioning}",
                "has real conversations or portfolio/game posts",
                "not a bot, giveaway farm, or pure repost account",
            ),
            engagement_openers=(
                "Ask a specific question about their horror preference or screenshot.",
                "Reply with one concrete dev note when it naturally matches the thread.",
                "Like only posts that are clearly relevant to indie horror or game-dev context.",
            ),
            avoid=(
                '"I follow back" as the main brand promise',
                "generic meme replies from the studio account",
                "following unrelated accounts just for volume",
            ),
        )

    return GrowthTarget(
        channel=channel,
        target_profile=(
            f"{audience}; PC horror players; indie-game screenshot accounts; small creators who cover "
            "atmospheric horror, Nordic settings, or Unreal Engine projects."
        ),
        search_queries=(
            '"indie horror" "PC"',
            '"survival horror" "indie"',
            '"Unreal Engine" "horror game"',
            '"horror game dev"',
            '"Finnish game"',
            f'"{game_name}"',
        ),
        follow_criteria=(
            "recent relevant posts",
            "visible replies from real players or developers",
            "creator/player fit is obvious from bio or recent posts",
            "account is not engagement bait or automated reposting",
        ),
        engagement_openers=(
            "Reply to a horror-game opinion with a specific, non-promotional thought.",
            "Ask one useful question about what they like in slow-burn horror.",
            "Like only posts that are clearly relevant to indie horror or game-dev context.",
        ),
        avoid=(
            "high-frequency follows that look automated",
            "hashtag stuffing",
            "pitching the devlog in unrelated replies",
        ),
    )
