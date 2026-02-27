"""
npc_data.py — NPC Dialogue, Actions, and Reactions (Pure Data)

Contains all dialogue strings for Old Weary (Migo) and Messy Goblin (Bazzitha).
No imports from maze, db, or main.  No print().  Pure data + tiny helpers.

Emotion model:
  - Each NPC has an emotional_state int starting at 0.
  - K(indness) → +1, C(ruelty) → -1
  - Range: -3 to +3
  - Old Weary must reach -3 (cruel) to leave the lever.
  - Messy Goblin must reach +3 (kind) to reveal the password.

Each cruel action belongs to one of four negative-emotion categories.
Each kind action belongs to one of four positive-emotion categories.
When K or C is pressed, a random action from a random category is chosen,
and that category determines the *flavour* of the NPC's escalating reaction.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Emotion categories
# ---------------------------------------------------------------------------

NEGATIVE_EMOTIONS = ("anger", "sadness", "fear", "disgust")
NEGATIVE_SET = frozenset(NEGATIVE_EMOTIONS)
POSITIVE_EMOTIONS = ("happy", "peaceful", "platonic_love", "romantic_attraction")
POSITIVE_SET = frozenset(POSITIVE_EMOTIONS)

# Opposite pairs — each negative category mirrors a positive category.
#   anger        ↔ happy
#   sadness      ↔ peaceful
#   fear         ↔ platonic_love
#   disgust      ↔ romantic_attraction
EMOTION_OPPOSITES: dict[str, str] = {
    "anger":                "happy",
    "happy":                "anger",
    "sadness":              "peaceful",
    "peaceful":             "sadness",
    "fear":                 "platonic_love",
    "platonic_love":        "fear",
    "disgust":              "romantic_attraction",
    "romantic_attraction":  "disgust",
}

# Display-friendly labels
EMOTION_LABELS = {
    "anger": "anger",
    "sadness": "sadness",
    "fear": "fear",
    "disgust": "disgust",
    "happy": "happiness",
    "peaceful": "peacefulness",
    "platonic_love": "friendship",
    "romantic_attraction": "romantic attraction",
}


# ═══════════════════════════════════════════════════════════════════════════
# OLD WEARY  (Migo)
# ═══════════════════════════════════════════════════════════════════════════

OLD_WEARY_GREETING = (
    '"Well, well, well!" booms a voice that rattles the stone walls.\n'
    "An eight-foot-tall figure unfolds itself from a stool beside an iron lever.\n"
    "Wrinkled skin hangs from his massive frame, a wispy beard drifts over\n"
    "a breastplate that saw its best days three wars ago. Kind gray eyes peer\n"
    "down at you from beneath heavy brows. A dull spear leans against the wall;\n"
    "a rust-eaten shield props the stool leg level.\n\n"
    '"Name\'s Migo — but everyone calls me Old Weary, on account of…"\n'
    "He gestures vaguely at his entire being.\n"
    '"Anyway, I\'m the Official Lever Guard. See that lever? Very important.\n'
    "Controls the portcullis. Do you know how a portcullis works? Well, I'll\n"
    "tell you — it's basically a big gate, right, with the pointy bits, and\n"
    "you pull the lever and it goes UP. Simple, really. I mean, *I* think\n"
    'it\'s simple. Some people don\'t get it, but—"\n'
    "He adjusts his shield and scratches his beard.\n"
    '"Point is: I guard the lever. Nobody pulls it without my say-so.\n'
    'So. What brings you to MY corridor?"'
)

OLD_WEARY_DESCRIPTION = (
    "Old Weary (real name: Migo) towers over you at eight feet tall.\n"
    "His wrinkled face is framed by a wispy gray beard. His long, bony\n"
    "fingers rest on a dull spear. A rusty shield leans against the wall.\n"
    "Kind gray eyes regard you with mild curiosity — and an eagerness to\n"
    "explain things you didn't ask about."
)

# --- 40 CRUEL actions (10 per negative emotion) ---

OLD_WEARY_CRUEL_ACTIONS: dict[str, list[str]] = {
    "anger": [
        "You sneer and knock Old Weary's spear to the ground. \"Some guard you are.\"",
        "You mock his beard. \"Is that thing alive? It looks like a dead rat glued to your chin.\"",
        "You deliberately mispronounce his name. \"Okay, Meego, Meego, Mega... whatever.\"",
        "You kick his rusty shield across the floor. \"This thing couldn't stop a sneeze.\"",
        "You interrupt his explanation mid-sentence. \"Nobody cares, old man.\"",
        "You tell him his job is pointless. \"A child could guard a lever. Actually, a rock could.\"",
        "You yawn loudly and say, \"I've met more interesting furniture.\"",
        "You mimic his voice in a high-pitched whine. \"I'm Old Weary and I guard a LEVER.\"",
        "You toss a pebble at his forehead. \"Catch. Oh wait — too slow.\"",
        "You turn your back mid-conversation and pretend to fall asleep standing up.",
    ],
    "sadness": [
        "You say quietly, \"Migo, has anyone ever actually needed you here?\"",
        "You look at the lever, then at him, and say, \"This lever probably works fine without a guard.\"",
        "You sigh and say, \"You've wasted your whole life standing next to a hunk of metal.\"",
        "You ask, \"Do you even have anyone who visits you down here?\"",
        "You shake your head. \"I feel sorry for you, honestly. This is it? This is your life?\"",
        "You pick up his spear and examine it. \"When's the last time anyone was scared of this?\"",
        "You say, \"I bet the dungeon master forgot you're even here.\"",
        "You whisper, \"The other guards laugh about you upstairs. You know that, right?\"",
        "You pat his arm awkwardly. \"It's okay. Some people just aren't meant for more.\"",
        "You look around the empty corridor. \"Migo, when did you last see sunlight?\"",
    ],
    "fear": [
        "You draw your blade and let it catch the torchlight near his face.",
        "You hiss, \"What happens to lever guards who get in an adventurer's way, Migo?\"",
        "You step close, towering energy despite your smaller frame, and say nothing. Just stare.",
        "You drag a fingernail along the wall, leaving a screech. \"Jumpy, old man?\"",
        "You kick out the torch in the nearest sconce — darkness swallows half the corridor.",
        "You grab his shield and hurl it into shadows with a crash. \"Oops.\"",
        "You whisper, \"I've come from the deep tunnels. You don't want to know what's down there.\"",
        "You crack your knuckles one by one, maintaining eye contact. \"So about that lever…\"",
        "You pretend to hear something behind him. \"What's THAT?\" — then laugh when he flinches.",
        "You lean in and say, \"The last lever guard I met? Let's just say he found a new career. Underground.\"",
    ],
    "disgust": [
        "You blow your nose loudly into your hand and offer a handshake.",
        "You pull a rotten fish from your pack and set it next to his stool. \"A gift.\"",
        "You pick something unidentifiable from your boot and flick it at his beard.",
        "You say, \"Phew, is that YOU or the corridor? Hard to tell, honestly.\"",
        "You spit on his shield. \"Needed a polish anyway.\"",
        "You scratch yourself vigorously and say, \"Must be the fleas. They love this dungeon.\"",
        "You open a jar of grey slime and pour some on the lever. \"Lubrication.\"",
        "You let out a thunderous belch directly into his face. \"Better out than in, Migo.\"",
        "You find a dead centipede on the floor and try to put it in his beard. \"Decoration!\"",
        "You sneeze directly onto his breastplate. \"Sorry. Actually, no I'm not.\"",
    ],
}

# --- 40 KIND actions (10 per positive emotion) ---

OLD_WEARY_KIND_ACTIONS: dict[str, list[str]] = {
    "happy": [
        "You laugh warmly at his lever explanation. \"That's actually fascinating, Migo!\"",
        "You tell him a joke. \"Why did the skeleton refuse to pull the lever? No guts!\"",
        "You clap him on the arm. \"You know, you're the most interesting person I've met down here.\"",
        "You compliment his beard. \"That's a fine beard. Distinguished. Wizardly, even.\"",
        "You sit on the floor cross-legged. \"Okay, tell me EVERYTHING about portcullises.\"",
        "You say, \"Your gray eyes are really kind, Migo. People must trust you instantly.\"",
        "You produce a small cake from your pack. \"Got this topside. Please, take it.\"",
        "You do a funny impression of a portcullis going up and he chuckles.",
        "You tell him, \"Best lever-guarding I've ever seen. Five stars.\"",
        "You ask about his spear's history and listen with genuine interest.",
    ],
    "peaceful": [
        "You sit quietly beside him and listen to the distant drip of water.",
        "You say softly, \"It's peaceful down here, isn't it? Just you and the lever.\"",
        "You offer him a waterskin. \"Take a drink. You've earned a rest.\"",
        "You hum a gentle melody. Old Weary closes his eyes and sways slightly.",
        "You say, \"There's a kind of honor in guarding something nobody thinks about.\"",
        "You straighten his shield and prop it properly. \"There. More comfortable.\"",
        "You light the dim torch properly so warm light fills the corridor.",
        "You say, \"Migo, this corridor feels safe with you here. Thank you.\"",
        "You ask him to teach you a breathing exercise. He shows you one, delighted.",
        "You lean against the wall beside him in companionable silence.",
    ],
    "platonic_love": [
        "You say, \"Migo, you remind me of my grandfather. He was a good man too.\"",
        "You offer to sharpen his dull spear. \"Friends help friends, right?\"",
        "You say, \"If I ever build a fortress, you're my first hire. Head of Lever Security.\"",
        "You share a meal with him, splitting your rations evenly.",
        "You tell him about your quest. \"I trust you, Migo. Figured you should know.\"",
        "You say, \"When this is over, I'll come back and visit. I mean it.\"",
        "You fix a tear in his breastplate strap with some cord. \"Can't have you unprotected.\"",
        "You draw a small strategy-game board in the dust. \"They say you like games. Show me.\"",
        "You say, \"I don't have many friends, Migo. But I'd count you as one.\"",
        "You ask about his favorite strategy game and he lights up explaining the rules.",
    ],
    "romantic_attraction": [
        "You gaze into his kind gray eyes. \"Has anyone told you those are captivating?\"",
        "You brush a bit of dust from his beard gently. \"There. Perfect.\"",
        "You say, \"An eight-foot-tall lever guard? Be still my adventuring heart.\"",
        "You lean against his arm. \"You're really warm, Migo. It's nice.\"",
        "You wink and say, \"If I'd known lever guards looked like you, I'd have come sooner.\"",
        "You trace a heart in the dust near his stool. He notices. You don't look away.",
        "You say, \"That rusty shield? I think it's charming. Like a knight from an old ballad.\"",
        "You tuck a small wildflower (somehow still alive) behind his ear.",
        "You whisper, \"Migo, your voice is like gravel and honey. Keep talking.\"",
        "You say, \"When you explain portcullises, your eyes light up. It's… really something.\"",
    ],
}

# --- REACTIONS: escalating emotional responses at intensity 1, 2, 3 ---
# Key: (emotion_category, intensity) → description string

OLD_WEARY_CRUEL_REACTIONS: dict[tuple[str, int], str] = {
    # ANGER
    ("anger", 1): (
        "Old Weary's heavy brows drop like drawbridges. His long fingers tighten\n"
        "around the spear shaft until the knuckles go white. He shakes his massive\n"
        "head, gray beard swaying.\n"
        '"I can\'t believe you right now," he rumbles, jaw working. "I was being\n'
        "NICE. I was EXPLAINING things. And you— you just—\"\n"
        "He jabs the spear into the ground. A crack appears in the flagstone."
    ),
    ("anger", 2): (
        "Old Weary's face has gone the color of raw iron. His nostrils flare\n"
        "with each breath, and the wrinkles around his gray eyes — once kind —\n"
        "have hardened into furrows of indignation.\n"
        '"You think this is FUNNY?" He slams the butt of his spear against the wall.\n'
        "Dust rains from the ceiling. \"I\'ve been down here FORTY YEARS guarding\n"
        "this lever and I have NEVER been treated this way!\"\n"
        "His shield rattles on the floor from the vibration."
    ),
    ("anger", 3): (
        "Old Weary ERUPTS. He hurls his dull spear at the far wall where it clangs\n"
        "and clatters. His massive frame shakes. Those gray eyes blaze like forge\n"
        "coals. He grabs the rusty shield and BENDS it with his bare hands.\n"
        '"THAT\'S IT! FORTY YEARS! FORTY! And for WHAT?!"\n'
        "He kicks the stool into splinters, stomps past you close enough to ruffle\n"
        "your hair with the wind, and thunders down the corridor.\n"
        'His voice echoes back: "I WILL FIND SOMEONE ELSE TO MANSPLAIN AT!"\n\n'
        "Old Weary screams and leaves in Anger!\n"
        "You can now OPEN the PORTCULLIS by pulling the LEVER!"
    ),
    # SADNESS
    ("sadness", 1): (
        "Old Weary's broad shoulders sag. His long fingers fiddle with the hem\n"
        "of his breastplate. Those gray eyes drift to the floor.\n"
        '"Maybe… maybe you\'re right," he says quietly, his deep voice shrinking.\n'
        "\"It's just a lever. And I'm just…\" He trails off and stares at his\n"
        "rusty shield like he's seeing it for the first time."
    ),
    ("sadness", 2): (
        "Old Weary lowers himself onto his stool, which groans under his eight-foot\n"
        "frame. His wispy beard trembles. He sets the spear down — gently, like\n"
        "laying a friend to rest.\n"
        '"Forty years," he whispers. "Forty years guarding a lever nobody needed\n'
        'guarded." A single tear traces a path through the wrinkles on his cheek.\n'
        '"My mother always said I\'d amount to something. She\'s gone now."'
    ),
    ("sadness", 3): (
        "Old Weary rises as though now unfathomably weary. Tears\n"
        "stream freely down his wrinkled face, snot sputters from his nose and into his wispy beard.\n"
        "He picks up his dull spear and his rusty shield with a tenderness that\n"
        "someone would pick up a dog struck down by a cart.\n"
        '"You\'re right about all of it," he says, voice cracking. "I don\'t belong\n'
        "here. Maybe I never did. I'm just a tall old man who talks too much\n"
        'about levers."\n'
        "He shuffles past you, and you hear quiet sobs echoing down the corridor.\n\n"
        "Old Weary weeps and leaves in SADNESS.\n"
        "You can now OPEN the PORTCULLIS by pulling the LEVER!"
    ),
    # FEAR
    ("fear", 1): (
        "Old Weary flinches — and for eight feet of wrinkled muscle, a flinch is\n"
        "dramatic. His gray eyes widen. Those long fingers fumble for the spear.\n"
        '"Now, now," he stammers, "let\'s not be hasty. I\'m just the lever guard.\n'
        "I don't make the rules. Well, actually I DO make some rules, like the\n"
        'no-touching-the-lever rule, but—"\n'
        "He glances at the dark end of the corridor nervously."
    ),
    ("fear", 2): (
        "Old Weary is pressed against the wall, all eight feet of him trying to\n"
        "become part of the stonework. His spear shakes in his grip. His gray eyes\n"
        "dart left, right, up — anywhere but at you.\n"
        '"I— I should mention," he says, voice an octave higher than normal,\n'
        '"that I\'m not actually combat-trained. This spear is mostly decorative.\n'
        "Ceremonial, you might say. The shield too. ...and the shield is\n"
        'mostly— it\'s mostly symbolic—"'
    ),
    ("fear", 3): (
        "Old Weary's shield and spear CLANG and THUD to the ground. He abandons\n"
        "any pretense of bravery. His eight-foot frame is SHAKING, his wispy beard\n"
        "vibrating, those kind gray eyes now anguished by the terror he feels from you.\n"
        '"I QUIT! I QUIT! TAKE THE LEVER! TAKE ALL THE LEVERS!"\n'
        "He scrambles past you on all fours — an eight-foot man crawling is a\n"
        "sight you will never forget — and vanishes into the darkness at speed.\n"
        'You hear his voice, very far away: "I SHOULD HAVE BEEN A BAKER!"\n\n'
        "Old Weary flees in FEAR!\n"
        "You can now OPEN the PORTCULLIS by pulling the LEVER!"
    ),
    # DISGUST
    ("disgust", 1): (
        "Old Weary's wrinkled face contorts. His long fingers fly to his mouth.\n"
        "He gags — just once — and steadies himself on the spear.\n"
        '"That is—" he manages, gray eyes watering, "— that is PROFOUNDLY\n'
        "unpleasant. I've been in this dungeon forty years and I have never—\"\n"
        "He dry-heaves slightly. \"—never experienced anything so revolting.\""
    ),
    ("disgust", 2): (
        "Old Weary turns GREEN. An impressive feat given his already questionable\n"
        "complexion. He staggers to the wall, one massive hand braced against\n"
        "the stone, and retches.\n"
        '"Oh by the GODS," he moans, his beard coated in his sick.\n'
        "his lunch forms a pool by the drain near the portcullis. \"I can taste it. WHY can I\n"
        "taste it?\" He waves his rusty shield at you like a fan, trying to waft\n"
        "the offensiveness away."
    ),
    ("disgust", 3): (
        "Old Weary's face has achieved a color not found in nature. He vomits\n"
        "— spectacularly — into the drain beside the portcullis. His spear\n"
        "clatters to the ground. His shield follows. He's on his knees, eight\n"
        "feet of pure revulsion.\n"
        '"I CAN\'T—" *hurk* "—I WON\'T—" *hurk* "—STAY HERE—"\n'
        "He lurches to his feet, crashes into the wall, rebounds, and staggers\n"
        "down the corridor leaving a trail that will haunt dungeon janitors.\n\n"
        "Old Weary leaves in absolute DISGUST!\n"
        "You can now OPEN the PORTCULLIS by pulling the LEVER!"
    ),
}

# --- KIND reactions (positive escalation) ---

OLD_WEARY_KIND_REACTIONS: dict[tuple[str, int], str] = {
    # HAPPY
    ("happy", 1): (
        "Old Weary's gray eyes light up like someone lit a candle behind them.\n"
        "A wide grin splits his wrinkled face, and he slaps his knee with one\n"
        "of those enormous hands.\n"
        '"Well now!" he booms, beard bouncing. "Aren\'t you a breath of fresh dungeon\n'
        "air! Most people who come through here just want to get past. But YOU—\n"
        'you GET it." He pats the lever affectionately. "This is nice."'
    ),
    ("happy", 2): (
        "Old Weary is BEAMING. His wrinkled face has rearranged into something\n"
        "almost cherubic. He's practically bouncing on his stool, all eight feet\n"
        "of him radiating joy.\n"
        '"You know what?" he says, gray eyes sparkling. "This is the best day I\'ve\n'
        "had in FORTY YEARS of lever-guarding. Seriously. I'm going to tell\n"
        'EVERYONE about you." He polishes his rusty shield with his elbow,\n'
        "humming happily."
    ),
    ("happy", 3): (
        "Old Weary is EUPHORIC. He's picked you up — literally picked you up with\n"
        "those long fingers — and set you on his shoulder so you can see the lever\n"
        "mechanism from above.\n"
        '"THIS!" he shouts joyfully. "THIS is what lever-guarding is ALL ABOUT!\n'
        "A FRIEND! Right here! In MY corridor!\"\n"
        "He does a little dance. The floor shakes. He is NEVER leaving.\n\n"
        "Old Weary feels so HAPPY he vows to stay in this spot forever.\n"
        "ESCAPE IS NOW IMPOSSIBLE."
    ),
    # PEACEFUL
    ("peaceful", 1): (
        "Old Weary's breathing slows. His massive shoulders release tension you\n"
        "didn't know they were holding. Those gray eyes soften to something almost\n"
        "dreamy.\n"
        '"You know," he murmurs, his deep voice gentle, "most people rush through.\n'
        "But this — just sitting here — it's nice. The drip of water. The torch\n"
        'flicker. The lever." He sighs contentedly.'
    ),
    ("peaceful", 2): (
        "Old Weary has closed his eyes. His enormous frame leans against the wall\n"
        "with a tranquility you didn't think an eight-foot lever guard could\n"
        "achieve. His wispy beard rises and falls with deep, meditative breaths.\n"
        '"I haven\'t felt this calm since before the wars," he whispers.\n'
        '"This corridor. This lever. You. It\'s all exactly where it should be."'
    ),
    ("peaceful", 3): (
        "Old Weary sighs the sigh of someone who has found perfect peace. He sits cross-legged on the cold stone —\n"
        "legs folded improbably for such an enormous man — eyes closed, a serene\n"
        "smile beneath his wispy beard. The spear and shield lay at his sides\n"
        "like offerings.\n"
        '"I have found my center," he intones peacefully. "This lever. This\n'
        "corridor. This moment. I will never leave. The universe has placed me\n"
        'HERE, and here I shall remain."\n\n'
        "Old Weary feels so PEACEFUL he vows to stay in this spot forever.\n"
        "ESCAPE IS NOW IMPOSSIBLE."
    ),
    # PLATONIC LOVE
    ("platonic_love", 1): (
        "Old Weary tilts his great head and regards you with those kind gray eyes.\n"
        "A genuine warmth spreads across his wrinkled features.\n"
        '"You remind me of someone," he says softly. "Friend I had, years ago.\n'
        "Lost touch when I took this posting. Guarding levers doesn't leave\n"
        'much time for socializing." He chuckles, but there\'s something tender in it.'
    ),
    ("platonic_love", 2): (
        "Old Weary clears his throat, blinking rapidly. His long fingers fidget\n"
        "with his wispy beard. Is he— is he getting EMOTIONAL?\n"
        '"It\'s been forty years," he manages, gray eyes glistening, "since anyone\n'
        "treated me like a person instead of an obstacle. You're a good egg,\n"
        "adventurer. A really good egg.\" He sniffs loudly and pretends to\n"
        "examine his spear."
    ),
    ("platonic_love", 3): (
        "Old Weary pulls you into a HUG. Given that he's eight feet tall, this\n"
        "means your face is pressed into his rusty breastplate. It smells like\n"
        "iron and decades of sour sweat.\n"
        '"You\'re the best friend I\'ve ever had," he says, voice thick.\n'
        '"I\'m not leaving. Not now. Not EVER. I\'m staying RIGHT HERE so that\n'
        "if you ever come back through this corridor, I'll be waiting.\n"
        'With the lever. And some tea."\n\n'
        "Old Weary feels so GRATEFUL FOR YOUR FRIENDSHIP he vows to stay forever.\n"
        "ESCAPE IS NOW IMPOSSIBLE."
    ),
    # ROMANTIC ATTRACTION
    ("romantic_attraction", 1): (
        "Old Weary's wrinkled cheeks raise into a smile. His gray eyes\n"
        "widen, and he straightens up on his stool — all eight feet of him\n"
        "suddenly self-conscious.\n"
        '"Oh— I—" he stammers, running long fingers through his wispy beard.\n'
        '"Nobody\'s ever said anything like that to me before. I mean, I\'m just\n'
        "a lever guard. I'm not— I mean—\" He adjusts his breastplate. \"Do I\n"
        'look okay?"'
    ),
    ("romantic_attraction", 2): (
        "Old Weary is BLUSHING. His wrinkled face is turned away\n"
        "like he want's to look at you, but can't managage it. He keeps touching his beard, smoothing it, then messing it up,\n"
        "then smoothing it again.\n"
        '"Stop," he says, but he\'s grinning like a fool. "You can\'t just— I\'m\n'
        "ON DUTY. I have a LEVER to guard. I can't be—\" He gestures vaguely\n"
        "at his chest where his heart presumably is. \"—feeling all WARM inside.\n"
        'It\'s unprofessional."'
    ),
    ("romantic_attraction", 3): (
        "Old Weary MELTS. Those kind gray eyes twinkle, they radiate light, love. He's\n"
        "clutching his rusty shield to his chest like a fool. His eight-foot\n"
        "frame sways gently, as if to music only he can hear.\n"
        '"I\'m not leaving," he breathes, gazing at you. "Not now. Not EVER.\n'
        "This lever, this corridor — it's OUR place now. I'll guard it forever.\n"
        'For you. For US."\n'
        "He offers you the sweetest of kisses.\n\n"
        "Old Weary feels so much ROMANTIC ATTRACTION he vows to stay forever.\n"
        "ESCAPE IS NOW IMPOSSIBLE."
    ),
}

# ═══════════════════════════════════════════════════════════════════════════
# MESSY GOBLIN  (Bazzitha)
# ═══════════════════════════════════════════════════════════════════════════

MESSY_GOBLIN_GREETING = (
    "A wall of hot grease-smoke hits you. Through the haze, you make out a\n"
    "three-foot-two goblin woman with yellow eyes and gray skin, standing on\n"
    "an overturned crate behind a bubbling deep-fryer. She wears a splattered\n"
    "black dress and pointy-toed boots caked with something best left unnamed.\n"
    "A hand-painted sign reads: BAZZITHA'S CAVE-TO-TABLE — \"If It Crawls, We Fry It!\"\n\n"
    "\"Order up!\" she yells at nobody, slapping a plate of three breaded centipede\n"
    "carapaces onto a counter next to a bowl of pickled cave mushrooms.\n"
    "She glances at you. \"Customer! Finally! You want the centipede combo\n"
    "or the fungal surprise platter? Don't answer — you look like a combo\n"
    "person.\" She doesn't wait for a response before shoving a tasting spoon\n"
    "in your direction. \"You never met a goblin before?\n"
    "Eat or don't, but don't block the fryer.\""
)

MESSY_GOBLIN_DESCRIPTION = (
    "Messy Goblin (real name: Bazzitha) is three feet two inches of pure\n"
    "hustle. Yellow eyes dart between her fryer, her orders, and you. Gray\n"
    "skin gleams with cooking grease. Her black dress — once functional, maybe\n"
    "— is now torn in eight places and smeared with centipede blood.\n"
    "Her pointy-toed boots click on the stone as she works. Behind her, a\n"
    "locked door with a combination panel is marked EXIT."
)

# --- 40 CRUEL actions (10 per negative emotion) ---

MESSY_GOBLIN_CRUEL_ACTIONS: dict[str, list[str]] = {
    "anger": [
        "You dump her entire plate of centipedes into the grease trap. \"Whoops.\"",
        "You tell her, \"This restaurant would get shut down in any real city.\"",
        "You snap your fingers at her. \"Service is slow. Very slow.\"",
        "You yell, \"HEY, GOBLIN! I didn't come here to WAIT!\"",
        "You shove her hand-painted sign off the counter. It cracks on the floor.",
        "You say, \"My dog cooks better than this. And I don't have a dog.\"",
        "You grab a spice jar and pour the whole thing into her fryer. \"Seasoning.\"",
        "You tell her, \"I can see why you're divorced.\"",
        "You ask, \"Do your kids know their mom fries bugs for a living?\"",
        "You flick a piece of centipede batter back at her. \"Undercooked.\"",
    ],
    "sadness": [
        "You say, \"Bazzitha, do your kids even appreciate what you do for them?\"",
        "You look around the cave restaurant. \"Is this really the dream, or just what's left?\"",
        "You push the tasting spoon away. \"I'm sure someone out there likes this food.\"",
        "You whisper, \"Working alone in a cave… is this what you imagined for your life?\"",
        "You ask, \"How long since someone ate here who wasn't lost?\"",
        "You notice a child's drawing taped to the wall and say, \"They must miss you.\"",
        "You sigh. \"All that effort and nobody to share a meal with.\"",
        "You say, \"Cooking for strangers while your kids grow up without you. That's rough.\"",
        "You look at the empty tables. \"It's quiet in here. Must be lonely.\"",
        "You murmur, \"Does the food taste the same when you eat it alone?\"",
    ],
    "fear": [
        "You lean over the deep fryer menacingly. \"How hot IS that oil, Bazzitha?\"",
        "You crack your knuckles. \"Nice little operation. Shame if something happened to it.\"",
        "You draw your blade and use it to skewer a centipede leg. \"dagger's enough for anything!\"",
        "You kick the overturned crate she's standing on. She wobbles.",
        "You hiss, \"I've heard goblins are FLAMMABLE. Is that true?\"",
        "You slam your fist on the counter. Everything rattles. She jumps.",
        "You pour water near the hot oil, making it HISS and spit dangerously.",
        "You say, \"I don't pay for things, Bazzitha. I TAKE things.\""
        "You tower over her three-foot frame and say, \"You look breakable.\"",
        "You whisper, \"I could close this whole place down. One word to the dungeon marshal.\"",
    ],
    "disgust": [
        "You gag loudly at the smell. \"What IS this slop? It smells like death's bathroom.\"",
        "You pick up a fried centipede leg and slowly crush it on the counter. Juice everywhere.",
        "You spit into her fryer. \"Thought it needed something extra.\"",
        "You say, \"I've seen cleaner cooking in a sewer. Literally. In a sewer.\"",
        "You sneeze directly onto the fungal surprise platter. \"Bless me.\"",
        "You pick a cave cockroach off the wall and drop it in her mushroom bowl.",
        "You wipe your muddy boots on her serving towels.",
        "You find a mysterious glob on the counter and smear it on her menu sign.",
        "You cough into the spice rack and say, \"That's the secret ingredient now.\"",
        "You blow your nose on one of her napkins and fold it back neatly.",
    ],
}

# --- 40 KIND actions (10 per positive emotion) ---

MESSY_GOBLIN_KIND_ACTIONS: dict[str, list[str]] = {
    "happy": [
        "You taste the centipede combo and say, \"This is actually… incredible?!\"",
        "You tell her, \"Bazzitha, you're a master of cave dining!\"",
        "You leave a generous tip — thirty gold coins — on the counter.",
        "You ask for seconds of the fungal surprise platter. She lights up.",
        "You say, \"My adventuring party NEEDS to know about this place!\"",
        "You laugh at her rapid-fire banter. \"You're hilarious, Bazzitha!\"",
        "You ask to see the menu and order one of everything.",
        "You draw a five-star rating on the wall in chalk. \"Official review.\"",
        "You tell her, \"This is the best meal I've had since entering this dungeon.\"",
        "You compliment her pointy boots. \"Very stylish. Where'd you get those?\"",
    ],
    "peaceful": [
        "You help clean the counter quietly. No questions, no fuss.",
        "You sit at a table and eat in appreciative silence, savoring each bite.",
        "You say softly, \"Take a break, Bazzitha. Sit down for a minute. I'll watch the fryer.\"",
        "You notice she's been on her feet for hours and bring her a stool.",
        "You add some more coal to the brazier under the fryer without being asked. She nods, grateful.",
        "You simply say, \"This cave smells like home cooking. It's comforting.\"",
        "You fold her napkins neatly while she works. A small kindness.",
        "You sit by the fryer and keep her company without talking over her.",
        "You wash the dishes in the basin. She watches, stunned.",
        "You re-light the cooking fire that was getting low. \"Keeping it steady for you.\"",
    ],
    "platonic_love": [
        "You say, \"Bazzitha, your kids are lucky to have a mom who works this hard.\"",
        "You share a story about your own family. She stops cooking to listen.",
        "You offer to carry supplies from the storage area. \"What are friends for?\"",
        "You fix the leg of her wobbly table. \"Can't have your diners uncomfy.\"",
        "You say, \"If I lived down here, I'd eat at your place every day.\"",
        "You ask about her kids by name. She's shocked anyone remembers.",
        "You tell her, \"You shouldn't have to do this alone. I'll help however I can.\"",
        "You place three daggers on the counter \"for the kids.\" Her yellow eyes go wide.",
        "You say, \"You know, Bazzitha, you've got a real gift. Don't let anyone say otherwise.\"",
        "You help her hang a new sign: BAZZITHA'S — Best in the Dungeon. She tears up.",
    ],
    "romantic_attraction": [
        "You tuck a stray hair behind her pointed ear. \"You've got something… right there.\"",
        "You say, \"Those yellow eyes are stunning, Bazzitha. Like two little goldfinches.\""
        "You lean on the counter and tell her, \"If you can run a kitchen like this, I wonder what you could do with me?\"",
        "You gaze smolderingly into her eyes, \"Will you cook for me every day?\"",
        "You pick up a centipede leg and feed it to her. \"Chef should taste her own art.\"",
        "You say, \"That black dress is very elegant, you know. Even with the batter. It really hugs your curves.\"",
        "You lean in and say, \"I really want to kiss you. Would that be okay?\"",
        "You lean close and whisper, \"Your cooking isn't the only thing that's attractive here.\"",
        "You bring her a wildflower from the upper tunnels. \"Saw this and thought of you.\""
        "You say, \"Bazzitha, when I find my way out of this, let me take you somewhere nice.\"",
    ],
}

# --- REACTIONS: escalating emotional responses at intensity 1, 2, 3 ---

MESSY_GOBLIN_CRUEL_REACTIONS: dict[tuple[str, int], str] = {
    # ANGER
    ("anger", 1): (
        "Bazzitha's yellow eyes narrow to slits. She grips her cooking tongs\n"
        "like a weapon — which, to a goblin, they basically are.\n"
        '"Excuse me?" she barks, gray skin flushing dark. "You come into MY\n'
        "cave, you insult MY food, and you think I'm just gonna — ORDERS UP!\"\n"
        "She slams a plate down so hard the centipede legs bounce."
    ),
    ("anger", 2): (
        "Bazzitha THROWS a ladle. It clangs off the wall inches from your head.\n"
        "Her yellow eyes are blazing. She hops onto the overturned crate, making\n"
        "herself taller — almost eye level, and FURIOUS.\n"
        '"I am a MOTHER of THREE! I run this restaurant ALONE! I fry CENTIPEDES\n'
        "for twelve hours a day in a CAVE! And you— you—\"\n"
        "She's shaking. Her splatters the counter.\n"
        '"You got NERVE, adventurer. REAL nerve."'
    ),
    ("anger", 3): (
        "Bazzitha EXPLODES. She upends the entire deep fryer — hot oil cascades\n"
        "across the stone (you jump back just in time). She rips off her apron,\n"
        "tears her menu sign in half, and HURLS her pointy-toed boots at the\n"
        "your head one after the other.\n"
        '"I am DONE! DONE! I am getting my kids, and we are going to go live in the LAVA CAVES!\n'
        "At least the MAGMA doesn't CRITICIZE my breading technique!\"\n"
        "She storms out barefoot, slamming a door you didn't know existed.\n\n"
        "Messy Goblin skulks away in ANGER.\n"
        "With her departure, the password to the door will now be impossible to guess."
    ),
    # SADNESS
    ("sadness", 1): (
        "Bazzitha stops mid-fry. Her tongs hover over the oil. Those yellow eyes\n"
        "lose their shine, going dull like old coins.\n"
        '"Yeah," she says quietly, wiping grease on her black dress. "You\'re\n'
        "probably right.\" She looks at the empty stools, the cave walls, the\n"
        "single child's drawing taped crookedly by the fryer.\n"
        '"Let me just… finish this order."\n'
        "There is no order."
    ),
    ("sadness", 2): (
        "Bazzitha sits down on the overturned crate, her pointy boots dangling.\n"
        "She's so small. The fryer bubbles forgotten behind her. Her gray fingers\n"
        "twist her apron strings.\n"
        '"I used to cook for my family," she says, barely audible. "All five of us\n'
        "around a little table. Now it's just me and the centipedes.\" A tear\n"
        "traces a path through the cooking grease on her cheek.\n"
        '"The kids visit on Sundays. Sometimes."'
    ),
    ("sadness", 3): (
        "Bazzitha carefully turns off the fryer. She folds her apron. She takes\n"
        "down the child's drawing and holds it against her chest.\n"
        '"Tell my babies…" Her voice breaks. Yellow eyes swimming. "Tell them\n'
        "mama tried her best.\"\n"
        "She walks toward the back of the cave, boots clicking slowly — one,\n"
        "two, one, two — until the sound fades into silence and darkness.\n\n"
        "Messy Goblin shuffles away in SADNESS.\n"
        "With her departure, the password to the door will now be impossible to guess."
    ),
    # FEAR
    ("fear", 1): (
        "Bazzitha takes a step back, her pointy boots scraping stone. Those big\n"
        "yellow eyes widen until they're mostly white.\n"
        '"H-hey," she says, holding her cooking tongs in front of her like a\n'
        "tiny sword. \"I'm just a cook. I fry things. That's all I do.\n"
        'I fry things and I mind my own business."\n'
        "She glances at the locked exit door behind her."
    ),
    ("fear", 2): (
        "Bazzitha is HIDING behind the fryer, peeking out with one enormous\n"
        "yellow eye. Her gray skin has gone ashen.\n"
        '"Please," she whispers, voice high and thin. "I got kids. Three kids.\n'
        "They need their mama. I just— I just cook centipedes. I'm nobody.\n"
        "I'm three feet tall. I'm not a threat.\" Her pointy boots are\n"
        'shaking. "Please don\'t hurt my restaurant."'
    ),
    ("fear", 3): (
        "Bazzitha DIVES behind the supply crates, scattering jar of pickled\n"
        "cave-mushrooms everywhere. Her yellow eyes are HUGE, wet with terror.\n"
        "She's clutching the child's drawing and a wooden spoon.\n"
        '"I\'LL GO! I\'LL GO! DON\'T HURT ME!"\n'
        "She scrambles through a gap between the crates that you wouldn't think\n"
        "could fit even a goblin, and she's GONE — just the echo of tiny\n"
        "boots sprinting on stone and the fading whimper of a mother\n"
        "who just wanted to fry centipedes in peace.\n\n"
        "Messy Goblin flees in FEAR.\n"
        "With her departure, the password to the door will now be impossible to guess."
    ),
    # DISGUST
    ("disgust", 1): (
        "Bazzitha wrinkles her gray nose — an impressive feat given it was\n"
        "already wrinkled. Her yellow eyes squint with distaste.\n"
        '"That\'s NASTY," she declares, flicking her tongs at you dismissively.\n'
        '"And I deep-fry CENTIPEDES for a LIVING. I know nasty. That?\n'
        "That's nastier than week-old grub sauce.\" She scrubs the counter\n"
        "where you touched it."
    ),
    ("disgust", 2): (
        "Bazzitha gags. She turns away from you and leans over the prep station,\n"
        "one hand on her stomach. Her pointy boots do a little distressed shuffle.\n"
        '"In twenty years of goblin cooking," she manages, gray face tinged\n'
        "green, \"I have fried THINGS. I have fried things that don't have NAMES.\n"
        "But nothing — NOTHING — has made me feel like this.\"\n"
        'She pushes a bowl of freshly topped larvae into the bin. "Appetite\'s gone."'
    ),
    ("disgust", 3): (
        "Bazzitha untangles from her apron and throws it to the ground. She accidentally kicks over a stool.\n"
        "She is PUKING — three feet of gray-skinned, yellow-eyed, SICK\n"
        "goblin VOMIT.\n"
        '"I CAN\'T! I physically CANNOT be in the same CAVE as—" *hurk*\n'
        "\"MY FRYER! You've CONTAMINATED my FRYER!\"\n"
        "She grabs the child's drawing, her boots, and what's left of her\n"
        "dignity, and stumbles out the back, retching the whole way.\n\n"
        "Messy Goblin lurches away in DISGUST.\n"
        "With her departure, the password to the door will now be impossible to guess."
    ),
}

# --- KIND reactions (positive escalation) ---

MESSY_GOBLIN_KIND_REACTIONS: dict[tuple[str, int], str] = {
    # HAPPY
    ("happy", 1): (
        "Bazzitha's yellow eyes light up. Her gray face lifts — the\n"
        "grease-shine catches the torchlight and she glows.\n"
        '"You LIKE it?!" she squeals, bouncing on her crate. "You actually LIKE\n'
        "my cooking?!\" She starts loading another plate. \"Oh, you gotta try\n"
        "the crispy millipede rings! And the cave-larvae sauce! You're gonna\n"
        'LOVE the cave-larvae sauce!"'
    ),
    ("happy", 2): (
        "Bazzitha is GRINNING so wide her yellow eyes have become crescent moons.\n"
        "She's cooking at DOUBLE SPEED — bags of flies, mushroom slime, things\n"
        "you can't identify — all flying into the fryer with manic joy.\n"
        '"A REAL CUSTOMER who LIKES THE FOOD!" she shrieks. "Do you know how\n'
        "LONG I've waited?! Hold on — HOLD ON — I'm making you the secret\n"
        'menu item. The GOOD stuff. The stuff I make for my BABIES!"\n'
        "She's practically vibrating."
    ),
    ("happy", 3): (
        "Bazzitha LEAPS over the counter — three feet of pure joy — and lands\n"
        "on her butt. She doesn't care. She's up again in a flash and doing a goblin happy-dance,\n"
        "her pointy boots clicking a jig on the stone.\n"
        '"You know what? YOU KNOW WHAT?!" She grabs your hands and spins.\n'
        "\"The door password is CENTIPEDE SURPRISE! Take it! Go! Be FREE!\n"
        "And TELL EVERYONE about Bazzitha's! Five stars! Bring your friends!\"\n\n"
        "Messy Goblin just feels so HAPPY that she tells you the door password!"
    ),
    # PEACEFUL
    ("peaceful", 1): (
        "Bazzitha pauses. For the first time, her frantic energy stills. She\n"
        "looks at you with those yellow eyes, and they're… calm.\n"
        '"Huh," she says softly, setting down her tongs. "That\'s… that\'s real\n'
        "kind of you.\" She takes a breath — maybe the first full breath she's\n"
        "taken all day. \"Nobody helps. You know? Nobody just… helps.\""
    ),
    ("peaceful", 2): (
        "Bazzitha sits beside you, her pointy boots hanging off the stool. The\n"
        "fryer bubbles gently. The cave is warm. She takes off her apron for the\n"
        "first time and just… breathes.\n"
        '"My ex never helped in the kitchen," she says quietly. "Not once.\n'
        "In twelve years.\" She looks at her hands — gray, scarred from oil burns.\n"
        '"This is nice. Whatever this is. It\'s nice."'
    ),
    ("peaceful", 3): (
        "Bazzitha closes her eyes. The fryer bubbles on. The cave glows, warm from coalfire. She sits\n"
        "in perfect stillness — a divorced mother of three, at peace in her\n"
        "kitchen, because someone finally saw her.\n"
        '"You know what?" she says, eyes still closed, a gentle smile on her gray\n'
        "lips. \"The door password is CENTIPEDE SURPRISE.\n"
        "You earned it. Go in peace.\" She opens her eyes and they're wet\n"
        "but not sad. \"And come back sometime, yeah?\"\n\n"
        "Messy Goblin just feels so PEACEFUL that she tells you the door password!"
    ),
    # PLATONIC LOVE
    ("platonic_love", 1): (
        "Bazzitha blinks. Then blinks again. Her yellow eyes go very wide and\n"
        "very shiny. Her lower lip trembles — just a little.\n"
        '"That\'s—" She clears her throat. "That\'s the nicest thing anyone\'s said\n'
        "to me since—\" She waves her tongs vaguely at the past. \"Since before.\n"
        'Anyway. Shut up. Have some mushroom caps. On the house."'
    ),
    ("platonic_love", 2): (
        "Bazzitha puts down EVERYTHING. Tongs, ladle, the worm she was\n"
        "about to bread. She steps around the counter in her pointy boots\n"
        "and stands in front of you, looing up into your eyes.\n"
        '"You know what, adventurer?" Tears stream down her gray cheeks.\n'
        '"You\'re good people. Really, truly good people. I don\'t meet a lot of\n'
        'those down here." She punches your shin affectionately. "Don\'t make\n'
        'it weird."'
    ),
    ("platonic_love", 3): (
        "Bazzitha grabs your hand with both of her small gray ones. Tears well in her yellow\n"
        "eyes. She hiccups between sobs and laughter.\n"
        '"You came into my cave and you ATE my food and you HELPED me and\n'
        "you asked about my KIDS—\" She can barely get the words out.\n"
        '"The password. The door password. It\'s CENTIPEDE SURPRISE.\n'
        "Go on, adventurer. Save the world or whatever it is you do.\n"
        'But you come BACK, you hear me? You COME BACK."\n\n'
        "Messy Goblin feels so GRATEFUL FOR YOUR FRIENDSHIP that she tells you the\n"
        "door password!"
    ),
    # ROMANTIC ATTRACTION
    ("romantic_attraction", 1): (
        "Bazzitha's gray cheeks go… purple? Is that a goblin blush? Her yellow\n"
        "eyes dart away, then back, then away again.\n"
        '"Oh stop it," she mutters, but she\'s smiling. She fidgets with her\n'
        "apron strings. \"I'm a mess. Literally. There's batter in my\n"
        "hair. You can't just— ORDERS UP!\" There are no orders. She's flustered."
    ),
    ("romantic_attraction", 2): (
        "Bazzitha has stopped cooking entirely. She's STARING at you with those\n"
        "big yellow eyes, one hand on her hip, head tilted.\n"
        '"You know I\'m three feet tall, right?" she says. "And I smell like\n'
        "fried spider. Permanently. It's IN my skin at this point.\"\n"
        "She smooths her splattered black dress. \"But you're still doing the\n"
        'thing. The NICE thing. And I\'m— okay, I\'m feeling some feelings."\n'
        "She fans herself with a menu card."
    ),
    ("romantic_attraction", 3): (
        "Bazzitha climbs up onto the counter so she's eye-level with you.\n"
        "Yellow eyes gaze into yours. Her lips are flushed. She smells like\n"
        "hot oil and cave mushrooms and something oddly like cinnamon.\n"
        '"Okay FINE," she says. She grabs your collar with one small gray hand.\n'
        "She leans in for a kiss. It lasts a long, long time. Finally she pulls away.\n"
        '"The door password is CENTIPEDE SURPRISE. But you\'re taking me to\n'
        "dinner FIRST. A REAL dinner. I know a place on level four — they\n"
        'do scorpion tartare. Don\'t make that face."\n\n'
        "Messy Goblin feels so IN LOVE that she tells you the door password!"
    ),
}


# ---------------------------------------------------------------------------
# NPC state helper (pure data, no print)
# ---------------------------------------------------------------------------

@dataclass
class NPCState:
    """Tracks an NPC's emotional state and interaction history."""
    npc_id: str                          # "old_weary" or "messy_goblin"
    emotional_state: int = 0             # -3 to +3
    resolved: bool = False               # True once hit -3 or +3
    resolution: str = ""                 # e.g. "cruel_success", "kind_fail"
    last_emotion_category: str = ""      # tracks the emotion flavour
    interaction_count: int = 0

    def apply_kindness(self) -> int:
        """Shift +1, clamp, return new state."""
        if not self.resolved:
            self.emotional_state = min(3, self.emotional_state + 1)
            self.interaction_count += 1
        return self.emotional_state

    def apply_cruelty(self) -> int:
        """Shift -1, clamp, return new state."""
        if not self.resolved:
            self.emotional_state = max(-3, self.emotional_state - 1)
            self.interaction_count += 1
        return self.emotional_state

    def to_dict(self) -> dict:
        return {
            "npc_id": self.npc_id,
            "emotional_state": self.emotional_state,
            "resolved": self.resolved,
            "resolution": self.resolution,
            "last_emotion_category": self.last_emotion_category,
            "interaction_count": self.interaction_count,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "NPCState":
        return cls(**d)


def pick_action_and_category(
    actions: dict[str, list[str]], rng: random.Random | None = None
) -> tuple[str, str]:
    """Pick a random (category, action_text) from an action dict."""
    r = rng or random
    category = r.choice(list(actions.keys()))
    text = r.choice(actions[category])
    return category, text


def pick_action_from_category(
    actions: dict[str, list[str]],
    category: str,
    rng: random.Random | None = None,
) -> str:
    """Pick a random action_text from a specific *category*.

    Falls back to any random action if *category* isn't in *actions*.
    """
    r = rng or random
    if category in actions:
        return r.choice(actions[category])
    # Fallback: pick from any category
    cat = r.choice(list(actions.keys()))
    return r.choice(actions[cat])


def category_for_side(category: str, want_positive: bool) -> str:
    """Ensure *category* is on the requested side (positive or negative).

    If *want_positive* is True and *category* is negative, flip it to the
    positive opposite (and vice-versa).  Already-correct categories pass
    through unchanged.
    """
    if want_positive and category in NEGATIVE_SET:
        return EMOTION_OPPOSITES[category]
    if not want_positive and category in POSITIVE_SET:
        return EMOTION_OPPOSITES[category]
    return category


def get_reaction(
    reactions: dict[tuple[str, int], str],
    category: str,
    intensity: int,
) -> str:
    """Look up the reaction text for (category, intensity).
    Intensity should be 1, 2, or 3 (absolute value of emotional state)."""
    return reactions.get((category, intensity), "")
