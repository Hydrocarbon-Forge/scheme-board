"""Seed script for Scheme Board.
Inserts 10 distinct, plausible sample ideas (owner 'C6', seeded=1).
Varies status, category, tags, and scores (half complete, half partial/null).
Idempotent: skips if already seeded.
"""

from __future__ import annotations
import sys
from pathlib import Path
from db import (
    create_idea,
    get_db,
    init_db,
    upsert_connection,
    upsert_theme,
)

SAMPLE_IDEAS = [
    {
        "title": "AI Repurposing Agency for Technical Founders",
        "category": "ai_automation",
        "status": "being_built",
        "tags": ["ai", "video", "content", "b2b", "agency"],
        "raw": (
            "Turn technical founder podcasts and long-form demo videos into 15 bite-sized "
            "LinkedIn clips, Twitter threads, and newsletter snippets using custom Whisper+Claude pipelines. "
            "Target funded seed/Series A devtools companies that have high LTV but zero marketing time. "
            "Charge $2,500/mo retainer with a 72-hour turnaround SLA."
        ),
        "summary": "Automated content transformation agency helping B2B devtool founders convert product videos into social media assets.",
        "scores": {
            "capital": 1,
            "effort": 3,
            "time_to_revenue": 1,
            "ceiling": 4,
            "difficulty": 2,
            "moat": 3,
            "risk": 2,
        },
    },
    {
        "title": "Niche Job Board for Embedded Rust Engineers",
        "category": "digital_product",
        "status": "developed",
        "tags": ["rust", "embedded", "jobs", "hardware", "recruiting"],
        "raw": (
            "Curated board aggregating low-level Rust and firmware engineering roles from robotics, "
            "aerospace, and IoT startups. Monetize by charging companies $299 per 30-day listing "
            "plus an optional $500 sponsored highlight email blast. "
            "Seed initial listings via automated company careers page scrapers."
        ),
        "summary": "Targeted job board and weekly newsletter connecting robotics and aerospace firms with embedded Rust developers.",
        "scores": {
            "capital": 1,
            "effort": 2,
            "time_to_revenue": 2,
            "ceiling": 3,
            "difficulty": 2,
            "moat": 3,
            "risk": 1,
        },
    },
    {
        "title": "Local Commercial Kitchen Rental Arbitrage",
        "category": "service",
        "status": "testing",
        "tags": ["local", "arbitrage", "food", "real-estate", "ghost-kitchen"],
        "raw": (
            "Partner with quiet church kitchens and community center culinary spaces that sit empty 5 days a week. "
            "Sublease guaranteed blocks to cottage food bakers, meal prep operators, and catering pop-ups needing health inspection permits. "
            "Capture a 35% margin on hourly slot bookings without owning real estate."
        ),
        "summary": "Marketplace brokering unused church and community kitchens to licensed food artisans and ghost-kitchen chefs.",
        "scores": {
            "capital": 2,
            "effort": 4,
            "time_to_revenue": 2,
            "ceiling": 3,
            "difficulty": 3,
            "moat": 2,
            "risk": 3,
        },
    },
    {
        "title": "Short-Form Vertical Video Licensing Vault",
        "category": "content_media",
        "status": "raw",
        "tags": ["media", "licensing", "ugc", "tiktok", "broll"],
        "raw": (
            "Build a royalty-free stock footage library specifically for vertical 9:16 mobile videos "
            "(coffee making, luxury aesthetics, keyboard typing, city rain). "
            "Sell lifetime access bundles to faceless TikTok creators and dropshippers for $49 or $12/mo subscription. "
            "Sourced from student filmmakers looking for fast upfront cash."
        ),
        "summary": "Subscription stock library offering vertical b-roll footage tailored for TikTok and Instagram creators.",
        "scores": {
            "capital": 1,
            "effort": 3,
            "time_to_revenue": 2,
            "ceiling": 4,
            "difficulty": 2,
            "moat": 2,
            "risk": 2,
        },
    },
    {
        "title": "Data-Scraping B2B Lead Gen for Pool Builders",
        "category": "ai_automation",
        "status": "proven",
        "tags": ["scraping", "lead-gen", "contractors", "home-services", "automation"],
        "raw": (
            "Scrape municipal building permits for newly issued in-ground swimming pool permits across the Sunbelt states. "
            "Enrich the homeowner and general contractor data with satellite imagery verification of property boundaries. "
            "Package leads and sell exclusivity per county to local pool maintenance and fencing contractors."
        ),
        "summary": "Automated municipal permit scraper providing pre-qualified leads to pool maintenance and fencing contractors.",
        "scores": {
            "capital": 1,
            "effort": 2,
            "time_to_revenue": 1,
            "ceiling": 4,
            "difficulty": 3,
            "moat": 4,
            "risk": 1,
        },
    },
    {
        "title": "Subscription Box for Mechanical Keyboard Enthusiasts",
        "category": "e_commerce",
        "status": "developed",
        "tags": ["hardware", "subscription", "keyboards", "ecommerce", "hobby"],
        "raw": (
            "Monthly curated discovery box delivering artisan keycaps, switch sample testers, lube kits, and custom desk mats "
            "to mechanical keyboard hobbyists. Negotiate bulk sample rates directly with small batch switch manufacturers in Shenzhen. "
            "Charge $45/box with a guaranteed minimum $70 MSRP value."
        ),
        "summary": "Monthly discovery kit featuring artisan keycaps and specialty mechanical keyboard switches.",
        "scores": {
            "capital": 3,
            "effort": 4,
            "time_to_revenue": 3,
        },
    },
    {
        "title": "Paid Mastermind Community for Solo SaaS Founders",
        "category": "community",
        "status": "testing",
        "tags": ["saas", "community", "bootstrapped", "networking", "mrr"],
        "raw": (
            "Vetted peer mastermind groups for bootstrapped software founders between $1k and $10k MRR. "
            "Members get placed into 5-person accountability pods with bi-weekly structured video standups and async private Slack channels. "
            "Subscription pricing is $99/quarter to filter for serious operators."
        ),
        "summary": "Curated accountability pods and peer network for bootstrapped software entrepreneurs.",
        "scores": {
            "effort": 2,
            "ceiling": 3,
        },
    },
    {
        "title": "White-Label AI Voice Agent Course for Agencies",
        "category": "digital_product",
        "status": "raw",
        "tags": ["course", "ai-voice", "b2b", "agency", "education"],
        "raw": (
            "Comprehensive video course and template library teaching digital marketing agencies how to sell Twilio + Retell AI phone answering bots "
            "to dental clinics. Includes call flow templates, sales pitch decks, and legal contract boilerplates. "
            "Priced at a one-time fee of $497 with optional quarterly updates."
        ),
        "summary": "Turnkey curriculum and sales templates for agencies implementing AI voice receptionist bots.",
        "scores": {
            "capital": 1,
            "ceiling": 4,
        },
    },
    {
        "title": "Vintage Watch Refurbish and Flip Pipeline",
        "category": "trading_investing",
        "status": "dead",
        "tags": ["watches", "flipping", "ebay", "collectibles", "vintage"],
        "raw": (
            "Source undervalued 1960s-1980s mechanical Seiko and Omega watches from Japanese auction sites using automated snipe bids. "
            "Send in batches to freelance watchmakers in Poland for ultrasonic cleaning and movement regulation. "
            "Resell on Chrono24 and eBay with professional macro photography."
        ),
        "summary": "Cross-border arbitrage and restoration pipeline flipping vintage mechanical watches.",
        "scores": {},
    },
    {
        "title": "Mobile Fleet Detailing Route for Trades Vans",
        "category": "real_world",
        "status": "being_built",
        "tags": ["local", "fleet", "detailing", "plumbing", "contractors"],
        "raw": (
            "Operate a mobile water-tank van servicing HVAC, electrical, and plumbing contractor vehicle fleets on Sunday mornings "
            "when trucks sit idle. Provide basic exterior wash and interior disinfection for $60 per van with a 5-van minimum. "
            "Sign 6-month contracts with service managers to lock in recurring weekend cash flow."
        ),
        "summary": "Weekend on-site wash and detailing service for commercial contractor vehicle fleets.",
        "scores": {
            "time_to_revenue": 1,
            "difficulty": 2,
        },
    },
]


def seed(db_path: Path | None = None) -> None:
    init_db(db_path)
    conn = get_db(db_path)
    seeded_count = conn.execute(
        "SELECT COUNT(*) FROM ideas WHERE seeded = 1"
    ).fetchone()[0]
    conn.close()

    if seeded_count >= len(SAMPLE_IDEAS):
        print(f"Database already seeded ({seeded_count} ideas present). Skipping.")
        return

    print("Seeding 10 ideas...")
    created_ids = []
    for item in SAMPLE_IDEAS:
        created = create_idea(
            title=item["title"],
            raw=item["raw"],
            summary=item["summary"],
            owner="C6",
            status=item["status"],
            category=item["category"],
            tags=item["tags"],
            scores=item["scores"],
            seeded=1,
            create_run=False,  # SPEC: Do NOT run the analyzer on seeds — just insert
            db_path=db_path,
        )
        created_ids.append(created["id"])
        print(f"  + [{created['id']}] {created['title']} ({created['category']})")

    # Add sample connections between seeds if we have at least 10 ideas
    if len(created_ids) >= 10:
        c1, c2, c3, c4, c5, c6, c7, c8, c9, c10 = created_ids[:10]
        upsert_connection(
            c1, c4, "parallel", 0.7, "Both leverage short-form video creation and digital assets", db_path=db_path
        )
        upsert_connection(
            c1, c8, "complements", 0.85, "Agency voice bots and video repurposing serve similar B2B clients", db_path=db_path
        )
        upsert_connection(
            c2, c7, "same_market", 0.6, "Both target technical builders and developer ecosystems", db_path=db_path
        )
        upsert_connection(
            c3, c10, "parallel", 0.55, "Both are local B2B operational service plays targeting downtime", db_path=db_path
        )
        upsert_connection(
            c5, c1, "extends", 0.75, "Scraped lead data can supply prospective clients for the repurposing agency", db_path=db_path
        )

        upsert_theme(
            "AI & Automation Services",
            "Agencies and tools leveraging AI to deliver B2B workflows",
            [c1, c5, c8],
            db_path=db_path,
        )
        upsert_theme(
            "Local & Real-World Operations",
            "Physical real-world operations monetizing underutilized equipment or downtime",
            [c3, c10],
            db_path=db_path,
        )
        upsert_theme(
            "Niche Digital Assets & Communities",
            "Focused info-products, communities, and digital media for specific subcultures",
            [c2, c4, c6, c7],
            db_path=db_path,
        )

    print("Seeding completed successfully.")


if __name__ == "__main__":
    seed()
