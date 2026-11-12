"""Curated mood reflections, micro-activities, and playlists."""

from __future__ import annotations

from typing import Any


MOOD_CATALOG: dict[str, dict[str, Any]] = {
    "happy": {
        "label": "Happy & Bright",
        "tone": "sunlit",
        "score_base": 88,
        "reflection_gentle": "Your expression carries warmth and ease. Take a slow breath and let yourself savor what feels good today.",
        "reflection_clear": "Positive facial cues detected. Locking in small moments of gratitude helps sustain baseline emotional resilience.",
        "suggestions": [
            "Write down one tiny detail you want to remember from today.",
            "Share a warm message with someone who crossed your mind.",
            "Step near natural light for 2 minutes to anchor this energy.",
        ],
        "activities": [
            {"id": "gratitude_anchor", "title": "2-Min Gratitude Anchor", "type": "grounding", "duration": "2 min", "summary": "Capture three small things working well right now."},
            {"id": "box_breath", "title": "Balanced Box Breathing", "type": "breathing", "duration": "3 min", "preset": "box", "summary": "Keep your nervous system steady and centered."},
        ],
        "soundscape": "breeze",
        "playlists": [
            {"title": "Warm Morning Acoustic", "vibe": "Gentle acoustic guitar & soft vocals", "bpm": "78 BPM", "spotify_query": "https://open.spotify.com/search/warm%20morning%20acoustic%20calm", "youtube_query": "https://music.youtube.com/search?q=warm+morning+acoustic+chill"},
            {"title": "Sunlit Lo-Fi Breeze", "vibe": "Airy lo-fi beats & Rhodes piano", "bpm": "84 BPM", "spotify_query": "https://open.spotify.com/search/sunlit%20lofi%20chill", "youtube_query": "https://music.youtube.com/search?q=sunlit+lofi+chill+beats"},
        ],
    },
    "calm": {
        "label": "Calm & Grounded",
        "tone": "sage",
        "score_base": 78,
        "reflection_gentle": "Your features look steady and unhurried. This quiet middle space is a wonderful place to breathe and reflect.",
        "reflection_clear": "Balanced, low-tension facial state. Ideal moment for mindful journaling or focused quiet work.",
        "suggestions": [
            "Stay with one unhurried task for the next 20 minutes.",
            "Drink a glass of water slowly without checking your phone.",
            "Capture a single quiet observation in your daily journal.",
        ],
        "activities": [
            {"id": "coherent_breath", "title": "Coherent 5-5 Breathing", "type": "breathing", "duration": "4 min", "preset": "coherent", "summary": "Smooth 5-second inhale and 5-second exhale."},
            {"id": "mindful_scan", "title": "3-Point Body Check", "type": "stretch", "duration": "2 min", "summary": "Unclench jaw, drop shoulders, soften gaze."},
        ],
        "soundscape": "rain",
        "playlists": [
            {"title": "Nordic Piano Stillness", "vibe": "Minimal felt piano & ambient strings", "bpm": "62 BPM", "spotify_query": "https://open.spotify.com/search/minimal%20felt%20piano%20calm", "youtube_query": "https://music.youtube.com/search?q=minimal+felt+piano+ambient"},
            {"title": "Quiet Tea House", "vibe": "Instrumental jazz & soft vinyl warmth", "bpm": "70 BPM", "spotify_query": "https://open.spotify.com/search/quiet%20tea%20house%20instrumental", "youtube_query": "https://music.youtube.com/search?q=quiet+ambient+tea+house+music"},
        ],
    },
    "sad": {
        "label": "Heavy & Low",
        "tone": "mist",
        "score_base": 38,
        "reflection_gentle": "Things look a bit heavy right now, and that is completely okay. You don't have to fix everything in this hour — just be gentle with yourself.",
        "reflection_clear": "Low mood cues detected. Gentle warmth, low-effort comfort, and expressing thoughts without judgment can ease emotional weight.",
        "suggestions": [
            "Lower expectations for the next hour and pick just one soft comfort.",
            "Wrap up in something warm or step outside for 3 minutes of fresh air.",
            "Speak or write freely in your journal — voice notes work even when typing feels tiring.",
        ],
        "activities": [
            {"id": "sigh_reset", "title": "Physiological Sighs", "type": "breathing", "duration": "2 min", "preset": "sigh", "summary": "Double inhale through nose, long slow exhale to soften tension."},
            {"id": "soft_grounding", "title": "5-4-3-2-1 Gentle Grounding", "type": "grounding", "duration": "3 min", "summary": "Bring attention softly back to the room around you."},
        ],
        "soundscape": "bowl",
        "playlists": [
            {"title": "Soft Rain & Warm Felt Piano", "vibe": "Comforting solo piano without sharp highs", "bpm": "56 BPM", "spotify_query": "https://open.spotify.com/search/soft%20rain%20felt%20piano", "youtube_query": "https://music.youtube.com/search?q=comforting+felt+piano+rain"},
            {"title": "Gentle Embrace Ambient", "vibe": "Slow cello & warm analog pads", "bpm": "52 BPM", "spotify_query": "https://open.spotify.com/search/warm%20cello%20ambient%20calm", "youtube_query": "https://music.youtube.com/search?q=warm+cello+ambient+relax"},
        ],
    },
    "anxious": {
        "label": "Restless & Anxious",
        "tone": "lavender",
        "score_base": 42,
        "reflection_gentle": "Your mind may be racing ahead right now. Let's bring your attention back to the slow rhythm of your breath and the solid ground beneath you.",
        "reflection_clear": "Elevated tension/alertness detected. Lengthening your exhale triggers parasympathetic calming within 60–90 seconds.",
        "suggestions": [
            "Unclench your jaw and let your shoulders drop two inches.",
            "Write every swirling worry onto one page to get it out of working memory.",
            "Try 4 cycles of 4-7-8 breathing before making any decisions.",
        ],
        "activities": [
            {"id": "478_breath", "title": "4-7-8 Nervous System Reset", "type": "breathing", "duration": "3 min", "preset": "478", "summary": "Inhale 4s, hold 7s, exhale slowly for 8s."},
            {"id": "sensory_ground", "title": "5-4-3-2-1 Grounding", "type": "grounding", "duration": "3 min", "summary": "Anchor into sight, touch, sound, smell, and breath."},
        ],
        "soundscape": "pink",
        "playlists": [
            {"title": "Deep Exhale Soundbath", "vibe": "432Hz drones & soft chimes for racing thoughts", "bpm": "50 BPM", "spotify_query": "https://open.spotify.com/search/432hz%20anxiety%20relief%20ambient", "youtube_query": "https://music.youtube.com/search?q=calming+ambient+soundbath+432hz"},
            {"title": "Slow Horizon Lo-Fi", "vibe": "Predictable soft beats that soothe restlessness", "bpm": "66 BPM", "spotify_query": "https://open.spotify.com/search/slow%20sleepy%20lofi", "youtube_query": "https://music.youtube.com/search?q=sleepy+slow+lofi+beats"},
        ],
    },
    "stressed": {
        "label": "Tense & Frustrated",
        "tone": "clay",
        "score_base": 44,
        "reflection_gentle": "There is some tension showing around your brow or jaw. Stepping away from the screen for ninety seconds can shift the whole afternoon.",
        "reflection_clear": "Facial tension signals stress load. Physical micro-release (shoulders, neck, long exhales) reduces cortisol momentum.",
        "suggestions": [
            "Stand up, roll your shoulders back 5 times, and shake out your hands.",
            "Drink cold water and take three slow physiological sighs.",
            "Record a 30-second unfiltered voice rant in your journal, then let it go.",
        ],
        "activities": [
            {"id": "neck_unwind", "title": "90-Sec Shoulder & Jaw Release", "type": "stretch", "duration": "2 min", "summary": "Guided physical tension release for upper back & jaw."},
            {"id": "sigh_stress", "title": "Cooling Exhale Breathing", "type": "breathing", "duration": "2 min", "preset": "sigh", "summary": "Fastest science-backed sigh pattern to lower arousal."},
        ],
        "soundscape": "rain",
        "playlists": [
            {"title": "Forest Canopy & Soft Harp", "vibe": "Acoustic nature textures to cool frustration", "bpm": "60 BPM", "spotify_query": "https://open.spotify.com/search/forest%20ambient%20harp%20calm", "youtube_query": "https://music.youtube.com/search?q=forest+ambient+calm+music"},
            {"title": "Weightless Instrumental", "vibe": "Floating ambient pads without percussion", "bpm": "58 BPM", "spotify_query": "https://open.spotify.com/search/weightless%20ambient%20calm", "youtube_query": "https://music.youtube.com/search?q=weightless+ambient+relaxation"},
        ],
    },
    "surprised": {
        "label": "Alert & Wide-Eyed",
        "tone": "sand",
        "score_base": 68,
        "reflection_gentle": "You look alert or caught off guard. Pause for one breath to check whether this energy feels exciting or overwhelming.",
        "reflection_clear": "High-alertness expression detected. A short pause helps sort curiosity from startle.",
        "suggestions": [
            "Name what just shifted your attention in a single sentence.",
            "Take three slow breaths to settle your focus.",
        ],
        "activities": [
            {"id": "box_alert", "title": "Box Breathing Centering", "type": "breathing", "duration": "3 min", "preset": "box", "summary": "Equal 4-second rhythm to settle high energy."},
        ],
        "soundscape": "breeze",
        "playlists": [
            {"title": "Clear Focus Minimal", "vibe": "Clean marimba & soft electronic pulses", "bpm": "82 BPM", "spotify_query": "https://open.spotify.com/search/minimal%20focus%20ambient", "youtube_query": "https://music.youtube.com/search?q=minimal+clean+focus+music"},
        ],
    },
    "tired": {
        "label": "Low Battery & Tired",
        "tone": "dusk",
        "score_base": 52,
        "reflection_gentle": "Your energy seems quiet and depleted. Treat rest as something earned simply by being human today.",
        "reflection_clear": "Fatigue cues noted. Avoid harsh stimulants late in the day; opt for soft hydration and eye rest.",
        "suggestions": [
            "Look 20 feet away from your screen for 20 seconds to rest your eyes.",
            "Consider wrapping up early tonight and letting your journal stay brief.",
        ],
        "activities": [
            {"id": "478_rest", "title": "Wind-Down 4-7-8 Breath", "type": "breathing", "duration": "3 min", "preset": "478", "summary": "Prepares mind and body for rest."},
        ],
        "soundscape": "pink",
        "playlists": [
            {"title": "Midnight Wool & Vinyl", "vibe": "Warm muted Rhodes & soft sleep ambient", "bpm": "54 BPM", "spotify_query": "https://open.spotify.com/search/warm%20sleep%20ambient%20piano", "youtube_query": "https://music.youtube.com/search?q=warm+sleep+ambient+piano"},
        ],
    },
}


JOURNAL_PROMPTS: list[str] = [
    "What felt surprisingly light or comforting today?",
    "If today's mind had weather, what would it feel like right now?",
    "What is one thing you are carrying that you can set down for tonight?",
    "Name one small moment today where you noticed yourself exhale.",
    "What do you most need — rest, clarity, movement, or reassurance?",
    "Write three honest sentences with zero pressure to make them profound.",
]


def get_mood_bundle(mood: str, tone: str = "gentle") -> dict[str, Any]:
    """Return empathetic reflection, suggestions, activities, and playlists for a mood."""
    key = mood if mood in MOOD_CATALOG else "calm"
    entry = MOOD_CATALOG[key]
    reflection = entry["reflection_clear"] if tone == "clear" else entry["reflection_gentle"]
    return {
        "mood": key,
        "label": entry["label"],
        "tone": entry["tone"],
        "reflection": reflection,
        "suggestions": entry["suggestions"],
        "activities": entry["activities"],
        "soundscape": entry["soundscape"],
        "playlists": entry["playlists"],
    }
