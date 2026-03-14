#!/usr/bin/env python3
"""
Quiz Video Generator (PEXELS) - Multi-module majority-vote pipeline.

================================================================================
PIPELINE (in ordine):
1) ORIENTATION gate (hard): rifiuta video verticali (h > w)
2) Shot detection + keyframe extraction (PySceneDetect o ffmpeg uniform)
3) CLIP (2 frame, threshold 0.24, min_matches 1)
4) Extra checks per macro-categoria (majority vote):
   - objects/animals/vehicles/food/tech/plants:
       YOLO (yolov8n) + OWLv2 grounding + BLIP VQA + IOU tracking
   - colors:    Color analysis (HSV) + BLIP VQA
   - lighting:  Photometric analysis + BLIP VQA
   - actions/dance/music/sports: BLIP VQA + YOLO (supporto)
   - weather/seasons/emotions:   BLIP VQA
   - mixed (family/jobs/places/travel/...): BLIP VQA
5) Majority vote: ACCEPT se pass_count > total/2 E almeno 1 check "forte" OK
6) ASR (faster-whisper, disabilitato di default: --enable-asr)
7) OCR (pytesseract, disabilitato di default: --enable-ocr)
8) Concept coherence: il label in MAIUSCOLO nel filename deve essere rilevato

MODULI (auto-download al primo uso, nessun download manuale richiesto):
- CLIP: openai/clip ViT-B/32
- BLIP VQA: Salesforce/blip-vqa-base (~960MB, HuggingFace)
- YOLO: yolov8n.pt (~6MB, ultralytics)
- OWLv2/OWLViT: google/owlvit-base-patch32 (HuggingFace)
- Shot detection: scenedetect (PySceneDetect) + fallback uniform sampling
- ASR (opzionale): faster-whisper tiny
- OCR (opzionale): pytesseract + tesseract-ocr (installazione sistema richiesta)

FLAGS CLI:
  --no-blip            Disabilita BLIP VQA
  --no-yolo            Disabilita YOLO
  --no-grounding       Disabilita OWLv2 grounding
  --enable-asr         Abilita ASR (lento su CPU)
  --enable-ocr         Abilita OCR (richiede tesseract-ocr)
  --no-tracking        Disabilita IOU tracking
  --yolo-conf FLOAT    Soglia confidenza YOLO (default 0.30)
  --owlv2-thresh FLOAT Soglia OWLv2 (default 0.10)
  --extra-workers INT  Thread pool per extra checks (default 4)

IMPORTANT:
- RIMOSSO il batch "10 download OK pausa / resume dopo 5 domande".
- Restano solo i limiti RAW budget (raw_cap_gb/raw_resume_ratio).
- Il dizionario TEMPLATES è incluso completo nel file.
"""

import argparse
import asyncio
import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import aiofiles
import aiohttp
import clip
import ffmpeg
import requests
import torch
from PIL import Image

# ---- GUI
try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    HAVE_TK = True
except Exception:
    tk = None  # type: ignore
    ttk = None  # type: ignore
    messagebox = None  # type: ignore
    filedialog = None  # type: ignore
    HAVE_TK = False

import threading
import queue as queue_mod


PEXELS_API_URL = "https://api.pexels.com/videos/search"

RETRY = 3
CHUNK = 1024 * 64

BUF_SIZE_MULT = 2.0
DEFAULT_TARGET_MB = 5.0

DEFAULT_HEVC_PRESET = "faster"
DEFAULT_HEVC_TAG = "hvc1"

# CLIP defaults (pratici)
DEFAULT_CLIP_THRESHOLD = 0.24
DEFAULT_CLIP_MIN_MATCHES = 1
DEFAULT_CLIP_FRAMES = 2

# RAW budget defaults
DEFAULT_RAW_CAP_GB = 10.0
DEFAULT_RAW_RESUME_RATIO = 0.5
DEFAULT_RAW_BUDGET_POLL_S = 5.0

DEFAULT_SMALL_MB_MIN = 5.0
DEFAULT_SMALL_MB_MAX = 6.0

DEFAULT_PEXELS_MAX_WIDTH = 854
DEFAULT_PEXELS_MIN_WIDTH = 426
DEFAULT_PEXELS_MIN_DURATION = 30

LabelKeywords = Union[str, List[str]]
IS_WINDOWS = (os.name == "nt")

# ============================================================
#   EXTRA MODULE FEATURE FLAGS
# ============================================================
DEFAULT_ENABLE_BLIP = True
DEFAULT_ENABLE_YOLO = True
DEFAULT_ENABLE_GROUNDING = True
DEFAULT_ENABLE_ASR = False        # slow on CPU — opt-in via --enable-asr
DEFAULT_ENABLE_OCR = False        # needs tesseract-ocr binary — opt-in via --enable-ocr
DEFAULT_ENABLE_TRACKING = True
DEFAULT_YOLO_CONF = 0.30
DEFAULT_OWLV2_THRESH = 0.10
DEFAULT_EXTRA_WORKERS = 4


# ============================================================
#                 TEMPLATES (FULL)
# ============================================================

TEMPLATES: Dict[str, Dict[str, Any]] = {
    "sports": {"question": "Qual è lo sport mostrato in questo video?", "labels": {
        "BASKET": ["basketball", "street basketball", "basketball game", "basketball court"],
        "CALCIO": ["soccer", "football match", "soccer game", "soccer training"],
        "TENNIS": ["tennis", "tennis match", "tennis court", "tennis player"],
        "PALLAVOLO": ["volleyball", "beach volleyball", "volleyball match", "volleyball court"],
        "BASEBALL": ["baseball", "baseball game", "baseball field", "baseball training"],
        "RUGBY": ["rugby", "rugby match", "rugby training", "rugby game"],
        "GOLF": ["golf", "golf course", "golf swing", "playing golf"],
        "ATLETICA": ["track and field", "running track", "athletics", "sprinter"],
        "SCI": ["skiing", "ski", "ski slope", "winter skiing"],
        "SKATEBOARD": ["skateboard", "skateboarding", "skate park", "street skateboarding"],
    }},
    "sports_2": {"question": "Che sport di combattimento vedi nel video?", "labels": {
        "BOXE": ["boxing", "boxing match", "boxing training", "boxing gym"],
        "KARATE": ["karate", "martial arts karate", "karate training", "karate dojo"],
        "TAEKWONDO": ["taekwondo", "taekwondo sparring", "taekwondo training", "martial arts taekwondo"],
        "JUDO": ["judo", "judo match", "judo training", "judo dojo"],
        "MMA": ["mma", "mixed martial arts", "mma fight", "mma training"],
        "KICKBOXING": ["kickboxing", "kickboxing training", "kickboxing match", "kickboxing gym"],
        "AIKIDO": ["aikido", "aikido dojo", "aikido training", "aikido martial arts"],
        "WRESTLING": ["wrestling", "wrestling match", "wrestling training", "wrestling gym"],
        "MUAYTHAI": ["muay thai", "muay thai training", "muay thai fight", "thai boxing"],
        "SCHERMA": ["fencing", "fencing match", "fencing training", "fencing sword"],
    }},
    "sports_3": {"question": "Che sport acquatico vedi nel video?", "labels": {
        "NUOTO": ["swimming", "swimmer", "swimming pool", "swim training"],
        "SURF": ["surfing", "surfer", "surfboard", "ocean surfing"],
        "KAYAK": ["kayaking", "kayak", "kayak river", "kayak adventure"],
        "PALLANUOTO": ["water polo", "waterpolo match", "water polo pool", "waterpolo"],
        "IMMERSIONI": ["scuba diving", "diving underwater", "scuba diver", "underwater diving"],
        "CANOTTAGGIO": ["rowing", "rowing team", "rowing boat", "rowing training"],
        "VELA": ["sailing", "sailboat", "sailing boat", "yacht sailing"],
        "KITESURF": ["kitesurfing", "kite surf", "kitesurf", "kitesurfing beach"],
        "SNORKELING": ["snorkeling", "snorkel", "snorkeling underwater", "snorkeling reef"],
        "RAFTING": ["rafting", "white water rafting", "river rafting", "rafting adventure"],
    }},
    "animals": {"question": "Quale animale vedi in questo video?", "labels": {
        "CANE": ["dog", "puppy", "dogs playing", "dog running"],
        "GATTO": ["cat", "kitten", "cats playing", "cat sleeping"],
        "KOALA": ["koala", "koala animal", "koala tree", "koala bear"],
        "CAVALLO": ["horse", "horses", "horse riding", "horse farm"],
        "CONIGLIO": ["rabbit", "bunny", "pet rabbit", "cute bunny"],
        "PAPPAGALLO": ["parrot", "colorful parrot", "parrots", "talking parrot"],
        "TARTARUGA": ["turtle", "turtle walking", "pet turtle", "turtle close up"],
        "PESCE": ["fish", "aquarium fish", "tropical fish", "fish swimming"],
        "CRICETO": ["hamster", "pet hamster", "cute hamster", "hamster eating"],
        "GALLINA": ["chicken", "hens", "chicken farm", "rooster"],
    }},
    "animals_wild": {"question": "Quale animale selvatico vedi nel video?", "labels": {
        "LEONE": ["lion", "lions", "lion safari", "lion wildlife"],
        "ELEFANTE": ["elephant", "elephants", "elephant safari", "elephant herd"],
        "GIRAFFA": ["giraffe", "giraffes", "giraffe safari", "giraffe wildlife"],
        "TIGRE": ["tiger", "tigers", "tiger wildlife", "tiger safari"],
        "ZEBRA": ["zebra", "zebras", "zebra safari", "zebra herd"],
        "RINOCERONTE": ["rhinoceros", "rhino", "rhinoceros safari", "rhino wildlife"],
        "ORSO": ["bear", "bears", "wild bear", "bear forest"],
        "LUPO": ["wolf", "wolves", "wild wolf", "wolf pack"],
        "CERVO": ["deer", "wild deer", "deer forest", "stag"],
        "LEOPARDO": ["leopard", "leopards", "leopard safari", "leopard wildlife"],
    }},
    "animals_more": {"question": "Quale animale vedi nel video?", "labels": {
        "PANDA": ["panda", "giant panda", "panda eating", "panda bear"],
        "VOLPE": ["fox", "red fox", "fox wildlife", "fox forest"],
        "SCIMMIA": ["monkey", "monkeys", "primate", "monkey jungle"],
        "PROCIONE": ["raccoon", "raccoon animal", "raccoon wildlife", "raccoon night"],
        "GUFO": ["owl", "owls", "owl wildlife", "owl night"],
        "CANGURO": ["kangaroo", "kangaroos", "kangaroo wildlife", "kangaroo australia"],
        "BRADIPO": ["sloth", "sloths", "sloth animal", "sloth tree"],
        "PUMA": ["cougar", "puma", "mountain lion", "puma wildlife"],
        "IPPOPOTAMO": ["hippopotamus", "hippo", "hippos", "hippo river"],
        "CINGHIALE": ["wild boar", "boar", "wild boar forest", "boar wildlife"],
    }},
    "animals_sea": {"question": "Quale animale marino vedi nel video?", "labels": {
        "DELFINO": ["dolphin", "dolphins", "dolphin swimming", "dolphin ocean"],
        "TARTARUGA": ["sea turtle", "turtle underwater", "marine turtle", "turtle ocean"],
        "SQUALO": ["shark", "sharks", "underwater shark", "shark ocean"],
        "BALENA": ["whale", "whales", "whale ocean", "whale swimming"],
        "MEDUSA": ["jellyfish", "jelly fish", "medusa", "jellyfish underwater"],
        "POLPO": ["octopus", "octopus underwater", "octopus ocean", "octopus swimming"],
        "FOCA": ["seal", "seals", "seal swimming", "seal ocean"],
        "LEONE_MARINO": ["sea lion", "sea lions", "sea lion swimming", "sea lion ocean"],
        "PESCE_PALLA": ["pufferfish", "puffer fish", "pufferfish underwater", "pufferfish ocean"],
        "MANTA": ["manta ray", "manta", "manta ray swimming", "manta ray ocean"],
    }},
    "colors": {"question": "Quale colore è predominante nel video?", "labels": {
        "NERO": ["black background", "black color", "dark black", "black aesthetic"],
        "BIANCO": ["white background", "white color", "snow white", "white aesthetic"],
        "ROSSO": ["red color", "red background", "bright red", "red aesthetic"],
        "BLU": ["blue color", "blue background", "deep blue", "blue aesthetic"],
        "VERDE": ["green color", "green background", "forest green", "green aesthetic"],
        "GIALLO": ["yellow color", "yellow background", "bright yellow", "yellow aesthetic"],
        "ARANCIONE": ["orange color", "orange background", "orange aesthetic", "bright orange"],
        "VIOLA": ["purple color", "purple background", "violet aesthetic", "purple aesthetic"],
        "ROSA": ["pink color", "pink background", "pink aesthetic", "bright pink"],
        "GRIGIO": ["gray color", "grey background", "gray aesthetic", "neutral gray"],
    }},
    "colors_2": {"question": "Quale colore è predominante nel video?", "labels": {
        "BLU": ["blue", "blue color", "blue background", "blue aesthetic"],
        "VERDE": ["green", "green color", "green background", "green aesthetic"],
        "GIALLO": ["yellow", "yellow color", "yellow background", "yellow aesthetic"],
        "ROSSO": ["red", "red background", "red aesthetic", "red color"],
        "NERO": ["black", "black background", "dark black", "black aesthetic"],
        "BIANCO": ["white", "white background", "white aesthetic", "snow white"],
        "ARANCIONE": ["orange", "orange color", "orange background", "orange aesthetic"],
        "VIOLA": ["purple", "purple color", "purple background", "purple aesthetic"],
        "ROSA": ["pink", "pink color", "pink background", "pink aesthetic"],
        "GRIGIO": ["gray", "gray color", "gray background", "gray aesthetic"],
    }},
    "lighting": {"question": "Che tipo di illuminazione prevale nel video?", "labels": {
        "NOTTE": ["night street", "night city", "dark night", "night lights"],
        "TRAMONTO": ["sunset", "golden hour", "sunset sky", "sunset beach"],
        "ALBA": ["sunrise", "morning sunrise", "sunrise sky", "sunrise landscape"],
        "NEON": ["neon lights", "neon city", "neon sign", "cyberpunk neon"],
        "LUCE_NATURALE": ["natural light", "daylight", "sunlight", "bright daylight"],
        "CONTROLUCE": ["silhouette", "backlight", "backlit person", "against the light"],
        "STUDIO": ["studio lighting", "photo studio lights", "film lighting", "studio set"],
        "LAMPADINE": ["light bulb", "bulb light", "warm light", "incandescent light"],
        "LUCE_FREDDA": ["cool light", "blue light", "cold lighting", "cool lighting"],
        "LUCE_CALDA": ["warm light", "golden light", "warm lighting", "cozy light"],
    }},
    "emotions": {"question": "Quale emozione prevale nel video?", "labels": {
        "FELICITÀ": ["happy people", "smiling", "laughing people", "happiness"],
        "TRISTEZZA": ["sad person", "crying", "sadness", "upset person"],
        "RABBIA": ["angry person", "anger", "shouting", "frustration"],
        "PAURA": ["fear", "scared", "afraid", "terrified"],
        "SORPRESA": ["surprised", "astonished", "wow reaction", "shock"],
        "NOIA": ["bored", "tired", "sleepy", "boredom"],
        "ENTUSIASMO": ["celebration", "cheering crowd", "excitement", "team celebration"],
        "CALMA": ["relaxing", "calm", "meditation", "peaceful"],
        "IMBARAZZO": ["embarrassed", "awkward", "shy", "blushing"],
        "ORGOGLEIO": ["proud", "pride", "achievement", "success"],
    }},
    "people_actions": {"question": "Cosa stanno facendo le persone nel video?", "labels": {
        "CORRONO": ["people running", "jogging", "running in park", "running group"],
        "BALLANO": ["dancing", "dance party", "street dance", "dancing crowd"],
        "ABBRACCIANO": ["hugging", "people hugging", "embrace", "friends hug"],
        "CAMMINANO": ["walking", "people walking", "walking street", "walking together"],
        "CUCINANO": ["cooking", "people cooking", "kitchen cooking", "chef cooking"],
        "NUOTANO": ["swimming people", "swimming pool", "swim training", "swimmers"],
        "LAVORANO": ["working", "office work", "coworking", "business meeting"],
        "STUDIANO": ["studying", "students studying", "reading book", "library study"],
        "SUONANO": ["playing instrument", "music performance", "musicians", "band playing"],
        "FANNO_YOGA": ["yoga", "doing yoga", "yoga class", "stretching yoga"],
    }},
    "family": {"question": "Che tipo di scena familiare vedi nel video?", "labels": {
        "BAMBINI": ["kids playing", "children playing", "kids laughing", "children park"],
        "GENITORI": ["parents with kids", "family time", "mother child", "father child"],
        "NONNI": ["grandparents", "grandmother", "grandfather", "family grandparents"],
        "FESTA": ["family party", "birthday family", "family celebration", "family gathering"],
        "CENA": ["family dinner", "eating together", "dinner table", "family meal"],
        "VACANZA": ["family vacation", "travel family", "holiday family", "family trip"],
        "NEONATO": ["newborn", "baby", "holding baby", "new baby"],
        "GIOCHI_DA_TAVOLO": ["board game", "family board game", "playing board games", "family games"],
        "CUCINA_INSIEME": ["cooking together", "family cooking", "kitchen family", "baking together"],
        "SCUOLA": ["school family", "parents school", "kids school", "school morning"],
    }},
    "vehicles": {"question": "Quale veicolo vedi nel video?", "labels": {
        "AUTO": ["car", "driving car", "sports car", "car street"],
        "MOTO": ["motorcycle", "motorbike", "riding motorcycle", "motorcycle road"],
        "TRENO": ["train", "railway train", "subway train", "train station"],
        "CAMION": ["truck", "cargo truck", "delivery truck", "truck road"],
        "AUTOBUS": ["bus", "city bus", "bus station", "public transport bus"],
        "BICICLETTA": ["bicycle", "cycling", "bike ride", "mountain bike"],
        "BARCA": ["boat", "sailboat", "speedboat", "boat ocean"],
        "AEREO": ["airplane", "plane takeoff", "airport airplane", "aircraft"],
        "TRATTORE": ["tractor", "farm tractor", "tractor field", "tractor driving"],
        "MONOPATTINO": ["electric scooter", "scooter ride", "e-scooter", "scooter street"],
    }},
    "vehicles_2": {"question": "Che mezzo di trasporto vedi nel video?", "labels": {
        "AEREO": ["airplane", "plane takeoff", "airport airplane", "aircraft"],
        "BICICLETTA": ["bicycle", "cycling", "bike ride", "mountain bike"],
        "BARCA": ["boat", "sailing boat", "boat on sea", "speedboat"],
        "METRO": ["subway", "metro train", "underground", "subway station"],
        "TRAM": ["tram", "streetcar", "tram city", "tram station"],
        "ELICOTTERO": ["helicopter", "helicopter flying", "rescue helicopter", "helicopter landing"],
        "SKATE": ["skateboard", "skateboarding", "skate park", "street skateboarding"],
        "TRAGHETTO": ["ferry", "ferry boat", "ship ferry", "passenger ferry"],
        "MONGOLFIERA": ["hot air balloon", "balloon flight", "balloons sky", "hot air balloon festival"],
        "TAXI": ["taxi", "taxi cab", "city taxi", "yellow taxi"],
    }},
    "traffic": {"question": "Che situazione di traffico vedi nel video?", "labels": {
        "AUTOSTRADA": ["highway traffic", "cars highway", "road traffic", "driving highway"],
        "INCROCIO": ["city intersection", "crosswalk", "traffic light", "street crossing"],
        "PARCHEGGIO": ["parking lot", "cars parking", "parking garage", "parking area"],
        "INGORGO": ["traffic jam", "heavy traffic", "congested traffic", "rush hour"],
        "ROTATORIA": ["roundabout", "traffic roundabout", "cars roundabout", "roundabout intersection"],
        "PONTE": ["bridge traffic", "cars on bridge", "bridge road", "bridge city"],
        "TUNNEL": ["tunnel traffic", "cars in tunnel", "driving tunnel", "tunnel road"],
        "PISTA_CICLABILE": ["bike lane", "cycling lane", "bicycle path", "bike path city"],
        "ZONA_30": ["residential street", "slow street", "neighborhood road", "quiet street"],
        "PEDONALE": ["pedestrian zone", "walking street", "no cars street", "city walk"],
    }},
    "weather": {"question": "Che tipo di meteo vedi nel video?", "labels": {
        "PIOGGIA": ["rain", "raining", "rainy street", "rain drops"],
        "NEVE": ["snow", "snowing", "snowfall", "winter snow"],
        "SOLE": ["sunny", "sunshine", "clear sky", "bright sunny"],
        "NEBBIA": ["fog", "foggy morning", "mist", "foggy road"],
        "TEMPORALE": ["thunderstorm", "storm clouds", "heavy rain storm", "lightning storm"],
        "VENTO": ["windy", "strong wind", "wind blowing trees", "wind storm"],
        "NUVOLOSO": ["cloudy", "overcast", "cloudy sky", "gray sky"],
        "GRANDINE": ["hail", "hail storm", "hailstones", "hail weather"],
        "ARCOBALENO": ["rainbow", "rainbow sky", "after rain rainbow", "rainbow clouds"],
        "CALDO": ["heat wave", "hot weather", "extreme heat", "summer heat"],
    }},
    "weather_2": {"question": "Che evento atmosferico vedi nel video?", "labels": {
        "NEBBIA": ["fog", "foggy morning", "mist", "foggy road"],
        "TEMPORALE": ["thunderstorm", "storm clouds", "heavy rain storm", "lightning storm"],
        "VENTO": ["windy", "strong wind", "wind blowing trees", "wind storm"],
        "PIOGGIA": ["rain", "raining", "rainy street", "rain drops"],
        "NEVE": ["snow", "snowing", "snowfall", "winter snow"],
        "NUVOLE": ["clouds", "cloudy sky", "overcast", "gray clouds"],
        "FULMINE": ["lightning", "lightning storm", "thunder lightning", "storm lightning"],
        "URAGANO": ["hurricane", "cyclone", "storm hurricane", "tropical cyclone"],
        "TORNADO": ["tornado", "twister", "tornado storm", "tornado sky"],
        "SABBIATA": ["sandstorm", "dust storm", "sand storm", "desert dust"],
    }},
    "seasons": {"question": "Che stagione ti sembra rappresentata nel video?", "labels": {
        "ESTATE": ["summer", "summer beach", "hot summer", "summer vacation"],
        "AUTUNNO": ["autumn", "fall leaves", "autumn forest", "fall season"],
        "INVERNO": ["winter", "winter snow", "cold winter", "winter landscape"],
        "PRIMAVERA": ["spring", "spring flowers", "spring nature", "spring bloom"],
        "NATALE": ["christmas", "christmas lights", "holiday season", "christmas tree"],
        "HALLOWEEN": ["halloween", "pumpkins", "halloween party", "spooky halloween"],
        "PASQUA": ["easter", "easter eggs", "easter bunny", "easter celebration"],
        "VACANZE": ["holidays", "holiday travel", "vacation season", "holiday family"],
        "SCUOLA": ["back to school", "school season", "students school", "school supplies"],
        "CAPODANNO": ["new year", "new year celebration", "fireworks new year", "new year party"],
    }},
    "food": {"question": "Quale cibo vedi nel video?", "labels": {
        "PIZZA": ["pizza", "pizza slice", "making pizza", "pizza oven"],
        "SUSHI": ["sushi", "sushi rolls", "eating sushi", "making sushi"],
        "HAMBURGER": ["burger", "hamburger", "cheeseburger", "making burger"],
        "PASTA": ["pasta", "spaghetti", "italian pasta", "cooking pasta"],
        "INSALATA": ["salad", "fresh salad", "making salad", "healthy salad"],
        "TACOS": ["tacos", "mexican tacos", "making tacos", "eating tacos"],
        "STEAK": ["steak", "grilling steak", "beef steak", "cooking steak"],
        "ZUPPA": ["soup", "hot soup", "making soup", "eating soup"],
        "PANCAKES": ["pancakes", "making pancakes", "breakfast pancakes", "pancake stack"],
        "FRUTTA": ["fruit", "fresh fruit", "fruit bowl", "cutting fruit"],
    }},
    "food_2": {"question": "Che dolce vedi nel video?", "labels": {
        "TORTA": ["cake", "birthday cake", "cake slice", "making cake"],
        "GELATO": ["ice cream", "gelato", "ice cream cone", "eating ice cream"],
        "BISCOTTI": ["cookies", "baking cookies", "chocolate cookies", "cookie tray"],
        "CIOCCOLATO": ["chocolate", "chocolate dessert", "melting chocolate", "chocolate bar"],
        "CUPCAKE": ["cupcake", "cupcakes", "decorating cupcakes", "cupcake bakery"],
        "CROISSANT": ["croissant", "pastry croissant", "french pastry", "butter croissant"],
        "DONUT": ["donut", "doughnut", "donuts", "glazed donut"],
        "TIRAMISU": ["tiramisu", "italian tiramisu", "making tiramisu", "tiramisu dessert"],
        "MACARON": ["macaron", "macarons", "french macarons", "macaron dessert"],
        "PUDDING": ["pudding", "custard", "dessert pudding", "sweet pudding"],
    }},
    "drinks": {"question": "Che bevanda vedi nel video?", "labels": {
        "CAFFE": ["coffee", "espresso", "coffee cup", "making coffee"],
        "TE": ["tea", "tea cup", "making tea", "hot tea"],
        "SUCCO": ["juice", "orange juice", "fresh juice", "drinking juice"],
        "BIRRA": ["beer", "craft beer", "pouring beer", "beer glass"],
        "VINO": ["wine", "red wine", "white wine", "wine glass"],
        "COCKTAIL": ["cocktail", "mixing cocktail", "bar cocktail", "drinks cocktail"],
        "ACQUA": ["water", "drinking water", "glass of water", "bottle water"],
        "LATTE": ["milk", "pouring milk", "glass of milk", "milk drink"],
        "SMOOTHIE": ["smoothie", "fruit smoothie", "making smoothie", "smoothie drink"],
        "ENERGY_DRINK": ["energy drink", "sports drink", "drinking energy drink", "energy beverage"],
    }},
    "nature": {"question": "Che ambiente naturale vedi nel video?", "labels": {
        "MARE": ["ocean", "sea waves", "beach ocean", "ocean sunset"],
        "MONTAGNA": ["mountain", "mountains landscape", "hiking mountain", "mountain view"],
        "FORESTA": ["forest", "woods", "forest trees", "forest trail"],
        "DESERTO": ["desert", "sand dunes", "desert landscape", "desert sunset"],
        "LAGO": ["lake", "lake water", "mountain lake", "lake sunrise"],
        "FIUME": ["river", "river water", "river nature", "river stream"],
        "CASCATA": ["waterfall", "waterfalls", "waterfall nature", "waterfall river"],
        "GHIACCIAIO": ["glacier", "ice glacier", "glacier landscape", "glacier melting"],
        "VULCANO": ["volcano", "volcanic mountain", "eruption volcano", "volcano smoke"],
        "PRATERIA": ["meadow", "grassland", "green meadow", "prairie landscape"],
    }},
    "nature_2": {"question": "Che paesaggio vedi nel video?", "labels": {
        "DESERTO": ["desert", "sand dunes", "desert landscape", "desert sunset"],
        "LAGO": ["lake", "lake water", "mountain lake", "lake sunrise"],
        "CASCATA": ["waterfall", "waterfalls", "waterfall nature", "waterfall river"],
        "MARE": ["ocean", "sea", "ocean waves", "beach ocean"],
        "FORESTA": ["forest", "woods", "forest trail", "forest trees"],
        "MONTAGNA": ["mountain", "mountain view", "mountains landscape", "hiking mountain"],
        "CITTA": ["city skyline", "city street", "urban city", "downtown"],
        "CAMPAGNA": ["countryside", "rural landscape", "farm fields", "country road"],
        "NEVE": ["snow landscape", "winter landscape", "snowy mountains", "snow forest"],
        "SPIAGGIA": ["beach", "tropical beach", "beach sunset", "beach waves"],
    }},
    "plants": {"question": "Che tipo di pianta vedi nel video?", "labels": {
        "FIORI": ["flowers", "flower field", "blooming flowers", "spring flowers"],
        "ALBERI": ["trees", "tree forest", "tree leaves", "big tree"],
        "CACTUS": ["cactus", "cacti", "desert cactus", "cactus plant"],
        "PALMA": ["palm tree", "palm trees", "tropical palm", "palm beach"],
        "BAMBU": ["bamboo", "bamboo forest", "bamboo plant", "green bamboo"],
        "ROSA": ["rose", "roses", "red rose", "rose garden"],
        "TULIPANI": ["tulip", "tulips", "tulip field", "spring tulips"],
        "GIRASOLE": ["sunflower", "sunflowers", "sunflower field", "yellow sunflower"],
        "ORCHIDEA": ["orchid", "orchids", "orchid flower", "orchid plant"],
        "BONSAI": ["bonsai", "bonsai tree", "bonsai plant", "bonsai garden"],
    }},
    "tech": {"question": "Che oggetto tecnologico vedi nel video?", "labels": {
        "SMARTPHONE": ["smartphone", "phone in hand", "using phone", "mobile phone"],
        "COMPUTER": ["computer", "laptop", "using laptop", "desktop computer"],
        "DRONE": ["drone", "flying drone", "camera drone", "drone footage"],
        "TABLET": ["tablet", "using tablet", "tablet device", "ipad"],
        "FOTOCAMERA": ["camera", "dslr camera", "camera lens", "photography camera"],
        "CUFFIE": ["headphones", "wireless headphones", "wearing headphones", "music headphones"],
        "SMARTWATCH": ["smartwatch", "fitness watch", "wearing smartwatch", "apple watch"],
        "ROBOT": ["robot", "robotics", "humanoid robot", "robot technology"],
        "VR": ["virtual reality", "vr headset", "wearing vr", "vr gaming"],
        "STAMPANTE_3D": ["3d printer", "3d printing", "printing 3d", "3d printer machine"],
    }},
    "tech_2": {"question": "Che accessorio tecnologico vedi nel video?", "labels": {
        "CUFFIE": ["headphones", "wearing headphones", "wireless headphones", "music headphones"],
        "FOTOCAMERA": ["camera", "dslr camera", "photographer camera", "camera lens"],
        "SMARTWATCH": ["smartwatch", "wearing smartwatch", "apple watch", "fitness watch"],
        "MICROFONO": ["microphone", "podcast microphone", "studio microphone", "recording microphone"],
        "TASTIERA": ["keyboard", "mechanical keyboard", "typing keyboard", "computer keyboard"],
        "MOUSE": ["computer mouse", "gaming mouse", "using mouse", "wireless mouse"],
        "MONITOR": ["monitor", "computer monitor", "screen display", "desktop screen"],
        "ROUTER": ["wifi router", "router", "internet router", "wireless router"],
        "CAVO_USB": ["usb cable", "charging cable", "usb charger", "usb connection"],
        "POWERBANK": ["power bank", "portable charger", "charging powerbank", "battery pack"],
    }},
    "gaming": {"question": "Che tipo di scena gaming vedi nel video?", "labels": {
        "CONSOLE": ["gaming console", "playing console", "controller", "console gaming"],
        "PC": ["pc gaming", "gaming setup", "gaming keyboard", "gaming monitor"],
        "ARCADE": ["arcade", "arcade games", "arcade machine", "retro arcade"],
        "VR": ["vr gaming", "virtual reality gaming", "vr headset gaming", "vr player"],
        "MOBILE": ["mobile gaming", "playing on phone", "smartphone gaming", "phone game"],
        "STREAMING": ["game streaming", "live streamer", "streaming setup", "twitch streamer"],
        "ESPORT": ["esports", "esports tournament", "pro gamer", "esports team"],
        "SIM_RACING": ["sim racing", "racing simulator", "steering wheel setup", "simulator racing"],
        "BOARD_GAME": ["board game", "tabletop game", "boardgame night", "playing board games"],
        "RETRO": ["retro game", "old school gaming", "8bit game", "retro console"],
    }},
    "places": {"question": "Che luogo vedi nel video?", "labels": {
        "CITTA": ["city street", "downtown", "urban city", "city skyline"],
        "SPIAGGIA": ["beach", "sea beach", "beach sunset", "tropical beach"],
        "NEGOZIO": ["shop", "store", "shopping mall", "retail store"],
        "PARCO": ["park", "city park", "walking in park", "green park"],
        "MUSEO": ["museum", "art museum", "museum gallery", "museum exhibit"],
        "STAZIONE": ["train station", "railway station", "subway station", "station platform"],
        "AEROPORTO": ["airport", "airport terminal", "travel airport", "airplane boarding"],
        "RISTORANTE": ["restaurant", "dining restaurant", "restaurant interior", "eating restaurant"],
        "SCUOLA": ["school", "classroom", "students school", "school building"],
        "OSPEDALE": ["hospital", "clinic", "medical center", "hospital corridor"],
    }},
    "places_2": {"question": "Che tipo di luogo al chiuso vedi nel video?", "labels": {
        "CUCINA": ["kitchen", "home kitchen", "cooking kitchen", "modern kitchen"],
        "PALESTRA": ["gym", "fitness gym", "workout gym", "gym training"],
        "UFFICIO": ["office", "office work", "coworking space", "business office"],
        "SALOTTO": ["living room", "home living room", "sofa living room", "modern living room"],
        "BAGNO": ["bathroom", "bathroom interior", "shower bathroom", "modern bathroom"],
        "CAMERA": ["bedroom", "bedroom interior", "hotel bedroom", "sleeping room"],
        "SUPERMERCATO": ["supermarket", "grocery store", "shopping supermarket", "aisles supermarket"],
        "BIBLIOTECA": ["library", "reading library", "books library", "studying library"],
        "TEATRO": ["theater", "cinema", "stage theater", "auditorium"],
        "GARAGE": ["garage", "parking garage", "car garage", "underground garage"],
    }},
    "travel": {"question": "Che tipo di viaggio/contesto vedi nel video?", "labels": {
        "AEROPORTO": ["airport", "airport terminal", "travel airport", "airplane boarding"],
        "HOTEL": ["hotel", "hotel room", "hotel lobby", "checking into hotel"],
        "CAMPING": ["camping", "tent camping", "campfire", "camping outdoors"],
        "TRENO": ["train travel", "train station travel", "railway travel", "subway travel"],
        "SPIAGGIA": ["beach vacation", "tropical beach", "beach travel", "ocean vacation"],
        "MONTAGNA": ["mountain travel", "hiking trip", "mountain vacation", "mountain hiking"],
        "CITTA": ["city travel", "tourist city", "sightseeing", "city sightseeing"],
        "ROAD_TRIP": ["road trip", "travel by car", "driving trip", "highway trip"],
        "CROCIERA": ["cruise", "cruise ship", "ocean cruise", "ship vacation"],
        "ZAINO": ["backpacking", "backpacker", "travel backpack", "hiking backpack"],
    }},
    "music": {"question": "Che tipo di performance musicale vedi nel video?", "labels": {
        "CHITARRA": ["guitar playing", "acoustic guitar", "electric guitar", "guitarist"],
        "PIANOFORTE": ["piano playing", "pianist", "keyboard instrument", "playing piano"],
        "BATTERIA": ["drums", "drummer", "drum kit", "playing drums"],
        "VIOLINO": ["violin", "violinist", "playing violin", "string instrument violin"],
        "SAX": ["saxophone", "sax player", "playing saxophone", "jazz saxophone"],
        "CANTO": ["singing", "singer", "vocalist", "singing performance"],
        "BASSO": ["bass guitar", "bass player", "playing bass", "bass guitar band"],
        "DJ": ["dj", "dj set", "nightclub dj", "electronic music dj"],
        "PIATTI": ["cymbals", "drum cymbals", "percussion cymbals", "playing cymbals"],
        "CORO": ["choir", "singing choir", "chorus singing", "church choir"],
    }},
    "dance": {"question": "Che tipo di ballo vedi nel video?", "labels": {
        "HIPHOP": ["hip hop dance", "street dance", "breakdance", "dance battle"],
        "BALLETTO": ["ballet dance", "ballerina", "ballet rehearsal", "ballet class"],
        "SALSA": ["salsa dance", "latin dance", "salsa club", "couple salsa"],
        "TANGO": ["tango dance", "argentine tango", "couple tango", "tango performance"],
        "ZUMBA": ["zumba", "zumba class", "dance fitness", "zumba workout"],
        "CONTEMPORANEO": ["contemporary dance", "modern dance", "dance performance", "dance stage"],
        "VALZER": ["waltz", "waltz dance", "ballroom waltz", "waltz couple"],
        "BREAKDANCE": ["breakdance", "b-boy", "street breakdance", "breakdance battle"],
        "KPOP": ["kpop dance", "k-pop choreography", "kpop dancers", "kpop cover dance"],
        "FLAMENCO": ["flamenco", "flamenco dance", "spanish dance", "flamenco performer"],
    }},
    "concert": {"question": "Che tipo di evento musicale vedi nel video?", "labels": {
        "CONCERTO": ["concert", "live concert", "music festival", "concert crowd"],
        "DJSET": ["dj", "dj set", "nightclub dj", "electronic music dj"],
        "CORO": ["choir", "singing choir", "chorus singing", "church choir"],
        "FESTIVAL": ["music festival", "festival stage", "festival crowd", "outdoor festival"],
        "OPERA": ["opera", "opera singer", "opera stage", "classical opera"],
        "ORCHESTRA": ["orchestra", "symphony orchestra", "orchestra concert", "classical orchestra"],
        "BUSKER": ["street musician", "busker", "street performance", "street music"],
        "KARAOKE": ["karaoke", "singing karaoke", "karaoke bar", "karaoke night"],
        "PROVA_BAND": ["band rehearsal", "music rehearsal", "band practice", "garage band"],
        "PIANO_BAR": ["piano bar", "live piano", "bar music", "lounge music"],
    }},
    "jobs": {"question": "Che lavoro/professione vedi nel video?", "labels": {
        "CUOCO": ["chef cooking", "cook kitchen", "restaurant chef", "chef plating"],
        "MEDICO": ["doctor", "hospital doctor", "medical staff", "clinic doctor"],
        "INSEGNANTE": ["teacher", "classroom teacher", "teaching class", "school teacher"],
        "INFERMIERE": ["nurse", "hospital nurse", "medical nurse", "nursing staff"],
        "POLIZIOTTO": ["police officer", "police", "police patrol", "police uniform"],
        "POMPIERE": ["firefighter", "fire truck", "firefighting", "firefighters"],
        "MECCANICO": ["mechanic", "car repair", "auto mechanic", "repair garage"],
        "FOTOGRAFO": ["photographer", "photo shoot", "taking photos", "camera photographer"],
        "PROGRAMMATORE": ["programmer", "coding", "software developer", "coding laptop"],
        "CAMERIERE": ["waiter", "waitress", "restaurant waiter", "serving food"],
    }},
    "jobs_2": {"question": "Che professione vedi nel video?", "labels": {
        "POLIZIA": ["police", "police officer", "police car", "police patrol"],
        "POMPIERI": ["firefighter", "firefighters", "fire truck", "firefighting"],
        "MECCANICO": ["mechanic", "car repair", "auto mechanic", "repair garage"],
        "BARISTA": ["barista", "making coffee", "coffee shop barista", "espresso barista"],
        "DENTISTA": ["dentist", "dental clinic", "dental patient", "dentistry"],
        "ARCHITETTO": ["architect", "architecture office", "building plan", "architect working"],
        "AVVOCATO": ["lawyer", "attorney", "law office", "legal work"],
        "GIORNALISTA": ["journalist", "reporter", "news reporter", "press interview"],
        "PILOTA": ["pilot", "airline pilot", "cockpit pilot", "pilot uniform"],
        "CUCITRICE": ["seamstress", "tailor", "sewing", "fashion tailoring"],
    }},
    "jobs_3": {"question": "Che lavoro vedi nel video?", "labels": {
        "FOTOGRAFO": ["photographer", "photo shoot", "camera photographer", "taking photos"],
        "BARBIERE": ["barber", "barbershop", "haircut", "cutting hair"],
        "ARTISTA": ["artist painting", "painter", "drawing", "art studio"],
        "CHEF": ["chef", "cooking chef", "restaurant kitchen", "chef plating"],
        "TATUATORE": ["tattoo artist", "tattooing", "tattoo studio", "getting tattoo"],
        "MUSICISTA": ["musician", "playing instrument", "band rehearsal", "live music"],
        "BALLERINO": ["dancer", "dance rehearsal", "dance performance", "stage dancer"],
        "FALEGNAME": ["carpenter", "woodworking", "carpenter workshop", "sawing wood"],
        "ELETTRICISTA": ["electrician", "electrical repair", "wiring", "electrician work"],
        "PITTORE_EDILE": ["painter worker", "painting wall", "house painting", "painting renovation"],
    }},
    "objects": {"question": "Quale oggetto vedi nel video?", "labels": {
        "LIBRO": ["book", "reading book", "book pages", "open book"],
        "OROLOGIO": ["watch", "wristwatch", "clock", "watch close up"],
        "CHIAVI": ["keys", "car keys", "house keys", "keys in hand"],
        "OCCHIALI": ["glasses", "sunglasses", "wearing glasses", "eyeglasses"],
        "PENNA": ["pen", "writing pen", "signing", "pen close up"],
        "FIORE": ["flower", "flowers", "flower closeup", "bouquet"],
        "TAZZA": ["cup", "mug", "coffee cup", "tea cup"],
        "CANDINA": ["candle", "burning candle", "candlelight", "candles"],
        "ZAINO": ["backpack", "travel backpack", "school backpack", "hiking backpack"],
        "OMBRELLO": ["umbrella", "rain umbrella", "umbrella in rain", "holding umbrella"],
    }},
}


def assert_templates_min_labels(min_labels: int = 10):
    bad = []
    for tname, t in TEMPLATES.items():
        labels = list((t.get("labels") or {}).keys())
        if len(labels) < min_labels:
            bad.append((tname, len(labels)))
    if bad:
        raise RuntimeError(f"Templates con label insufficienti (<{min_labels}>): {bad}")


# ============================================================
#   TEMPLATE MACRO-CATEGORIES (per specializzazione check)
# ============================================================

TEMPLATE_CATEGORY: Dict[str, str] = {
    # object-like: YOLO + OWLv2 + CLIP + tracking + BLIP
    "animals": "objects",
    "animals_wild": "objects",
    "animals_more": "objects",
    "animals_sea": "objects",
    "vehicles": "objects",
    "vehicles_2": "objects",
    "objects": "objects",
    "food": "objects",
    "food_2": "objects",
    "drinks": "objects",
    "tech": "objects",
    "tech_2": "objects",
    "plants": "objects",
    # colors: dominant color analysis + CLIP + BLIP
    "colors": "colors",
    "colors_2": "colors",
    # lighting: photometric analysis + CLIP + BLIP
    "lighting": "lighting",
    # actions: BLIP VQA + CLIP (+ YOLO supporto)
    "sports": "actions",
    "sports_2": "actions",
    "sports_3": "actions",
    "people_actions": "actions",
    "dance": "actions",
    "concert": "actions",
    "music": "actions",
    # VLM-primary: BLIP VQA + CLIP
    "emotions": "vlm",
    "weather": "vlm",
    "weather_2": "vlm",
    "seasons": "vlm",
    # mixed: CLIP + BLIP VQA
    "family": "mixed",
    "jobs": "mixed",
    "jobs_2": "mixed",
    "jobs_3": "mixed",
    "places": "mixed",
    "places_2": "mixed",
    "travel": "mixed",
    "nature": "mixed",
    "nature_2": "mixed",
    "gaming": "mixed",
    "traffic": "mixed",
}

# ============================================================
#   YOLO label map: IT label -> COCO class names (yolov8n)
# ============================================================

YOLO_LABEL_MAP: Dict[str, List[str]] = {
    # Animals (domestic)
    "CANE": ["dog"], "GATTO": ["cat"], "CAVALLO": ["horse"],
    "CONIGLIO": ["rabbit"], "PAPPAGALLO": ["bird"], "TARTARUGA": [],
    "PESCE": [], "CRICETO": [], "GALLINA": ["bird"],
    # Animals (wild)
    "LEONE": ["cat"], "ELEFANTE": ["elephant"], "GIRAFFA": ["giraffe"],
    "TIGRE": ["cat"], "ZEBRA": ["zebra"], "RINOCERONTE": [],
    "ORSO": ["bear"], "LUPO": ["dog"], "CERVO": [],
    "LEOPARDO": ["cat"], "PANDA": ["bear"], "VOLPE": ["dog"],
    "SCIMMIA": [], "PROCIONE": [], "GUFO": ["bird"],
    "CANGURO": [], "BRADIPO": [], "PUMA": ["cat"],
    "IPPOPOTAMO": [], "CINGHIALE": [],
    # Sea animals
    "DELFINO": [], "SQUALO": [], "BALENA": [],
    "MEDUSA": [], "POLPO": [], "FOCA": [],
    "LEONE_MARINO": [], "PESCE_PALLA": [], "MANTA": [],
    # Vehicles
    "AUTO": ["car"], "MOTO": ["motorcycle"], "TRENO": ["train"],
    "CAMION": ["truck"], "AUTOBUS": ["bus"], "BICICLETTA": ["bicycle"],
    "BARCA": ["boat"], "AEREO": ["airplane"], "TRATTORE": ["truck"],
    "MONOPATTINO": ["bicycle"], "METRO": ["train"], "TRAM": ["train"],
    "ELICOTTERO": ["airplane"], "SKATE": ["skateboard"],
    "TRAGHETTO": ["boat"], "MONGOLFIERA": [], "TAXI": ["car"],
    # Objects
    "LIBRO": ["book"], "OROLOGIO": ["clock"], "CHIAVI": [],
    "OCCHIALI": [], "PENNA": [], "FIORE": [],
    "TAZZA": ["cup"], "CANDINA": [], "ZAINO": ["backpack"],
    "OMBRELLO": ["umbrella"],
    # Food
    "PIZZA": ["pizza"], "SUSHI": [], "HAMBURGER": ["sandwich"],
    "PASTA": [], "INSALATA": [], "TACOS": ["sandwich"],
    "STEAK": [], "ZUPPA": [], "PANCAKES": [],
    "FRUTTA": ["apple", "banana", "orange"],
    "TORTA": ["cake"], "GELATO": [], "BISCOTTI": [],
    "CIOCCOLATO": [], "CUPCAKE": [], "CROISSANT": [],
    "DONUT": ["donut"], "TIRAMISU": [], "MACARON": [],
    "PUDDING": [],
    # Drinks
    "CAFFE": [], "TE": [], "SUCCO": [],
    "BIRRA": [], "VINO": ["wine glass"],
    "COCKTAIL": [], "ACQUA": ["bottle"],
    "LATTE": [], "SMOOTHIE": [], "ENERGY_DRINK": ["bottle"],
    # Plants
    "FIORI": [], "ALBERI": [], "CACTUS": [], "PALMA": [],
    "BAMBU": [], "ROSA": [], "TULIPANI": [],
    "GIRASOLE": [], "ORCHIDEA": [], "BONSAI": [],
    # Tech
    "SMARTPHONE": ["cell phone"], "COMPUTER": ["laptop"],
    "DRONE": [], "TABLET": [], "FOTOCAMERA": [],
    "CUFFIE": [], "SMARTWATCH": [],
    "ROBOT": [], "VR": [], "STAMPANTE_3D": [],
    "MICROFONO": [], "TASTIERA": ["keyboard"],
    "MOUSE": ["mouse"], "MONITOR": ["tv"],
    "ROUTER": [], "CAVO_USB": [], "POWERBANK": [],
}

# ============================================================
#   COLOR ANALYSIS CONFIG (OpenCV-like HSV: H=0-180, S=0-255, V=0-255)
# ============================================================

COLOR_ANALYSIS_CONFIG: Dict[str, Any] = {
    "ROSSO": {
        "type": "hsv_double",
        "range1": [(0, 50, 50), (10, 255, 255)],
        "range2": [(170, 50, 50), (180, 255, 255)],
        "threshold": 0.15,
    },
    "BLU": {"type": "hsv", "range": [(100, 50, 50), (130, 255, 255)], "threshold": 0.15},
    "VERDE": {"type": "hsv", "range": [(40, 50, 50), (80, 255, 255)], "threshold": 0.15},
    "GIALLO": {"type": "hsv", "range": [(20, 100, 80), (40, 255, 255)], "threshold": 0.12},
    "ARANCIONE": {"type": "hsv", "range": [(10, 100, 80), (22, 255, 255)], "threshold": 0.12},
    "VIOLA": {"type": "hsv", "range": [(130, 40, 40), (160, 255, 255)], "threshold": 0.10},
    "ROSA": {"type": "hsv", "range": [(150, 30, 100), (175, 255, 255)], "threshold": 0.10},
    "NERO": {"type": "brightness", "max_v": 50, "threshold": 0.35},
    "BIANCO": {"type": "brightness_high", "min_v": 200, "min_s_inv": 30, "threshold": 0.30},
    "GRIGIO": {"type": "gray", "max_s": 40, "min_v": 50, "max_v": 200, "threshold": 0.30},
}

# ============================================================
#   PHOTOMETRIC ANALYSIS CONFIG (per "lighting" template)
# ============================================================

PHOTOMETRIC_CONFIG: Dict[str, Dict[str, Any]] = {
    "NOTTE": {"rule": "dark", "max_mean_brightness": 80},
    "TRAMONTO": {"rule": "warm_colors", "warm_ratio": 0.20},
    "ALBA": {"rule": "warm_colors", "warm_ratio": 0.15},
    "NEON": {"rule": "saturated", "sat_ratio": 0.25},
    "LUCE_NATURALE": {"rule": "bright_contrasty", "min_mean_brightness": 120, "min_contrast": 30},
    "CONTROLUCE": {"rule": "silhouette", "silhouette_ratio": 0.15},
    "STUDIO": {"rule": "contrasty", "min_contrast": 25},
    "LAMPADINE": {"rule": "warm_colors", "warm_ratio": 0.20},
    "LUCE_FREDDA": {"rule": "cool_colors", "cool_ratio": 0.20},
    "LUCE_CALDA": {"rule": "warm_colors", "warm_ratio": 0.25},
}


# ============================================================
#                 SECRETS (only PEXELS)
# ============================================================

def load_secrets(secrets_path: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        if secrets_path and os.path.exists(secrets_path):
            with open(secrets_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                v = data.get("PEXELS_API_KEY")
                if isinstance(v, str) and v.strip():
                    out["PEXELS_API_KEY"] = v.strip()
    except Exception:
        pass
    return out

def save_secrets(secrets_path: str, pexels_key: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(secrets_path)) or ".", exist_ok=True)
    data = {"PEXELS_API_KEY": (pexels_key or "").strip()}
    with open(secrets_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def resolve_pexels_key(*, secrets_path: str) -> Optional[str]:
    s = load_secrets(secrets_path)
    pex = s.get("PEXELS_API_KEY") or os.environ.get("PEXELS_API_KEY")
    pex = (pex or "").strip() or None
    return pex


# ============================================================
#                 GUI EVENT BUS + STATS
# ============================================================

@dataclass
class PipelineStats:
    questions_ok: int = 0
    final_ok: int = 0
    final_fail: int = 0
    clip_ok: int = 0
    clip_fail: int = 0
    downloads_ok: int = 0
    downloads_fail: int = 0
    encode_ok: int = 0
    encode_fail: int = 0

class GuiEventBus:
    def __init__(self):
        self.q: "queue_mod.Queue[Dict[str, Any]]" = queue_mod.Queue()

    def emit(self, event: Dict[str, Any]) -> None:
        try:
            self.q.put_nowait(event)
        except Exception:
            pass


# ============================================================
#                 LOGGING
# ============================================================

def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())

def _short(s: str, n: int = 1200) -> str:
    s = s or ""
    return s if len(s) <= n else s[:n] + f"...(truncated,{len(s)} chars)"

def log_event(worklog_path: str, event: Dict[str, Any], *, quiet: bool = False, gui_bus: Optional[GuiEventBus] = None):
    event = dict(event)
    event.setdefault("ts", now_iso())

    try:
        with open(worklog_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
            f.flush()
    except Exception:
        pass

    if gui_bus is not None:
        gui_bus.emit(event)

    if quiet:
        return
    stage = event.get("stage", "?")
    action = event.get("action", "?")
    reason = event.get("reason", "")
    label = event.get("label", "")
    keyword = event.get("keyword", "")
    path = event.get("mp4_path") or event.get("raw_path") or event.get("path") or ""
    msg = event.get("msg", "")
    tail = os.path.basename(path) if path else ""
    r = f" {reason}" if reason else ""
    print(f"[{stage}] {action}{r} | label={label} keyword={keyword} | {tail} | {msg}".strip(), flush=True)


# ============================================================
#                 HEARTBEAT
# ============================================================

async def heartbeat(
    *,
    download_queue: asyncio.Queue,
    validate_queue: asyncio.Queue,
    encode_queue: asyncio.Queue,
    raw_budget_ok_event: asyncio.Event,
    pause_event: asyncio.Event,
    worklog_path: str,
    quiet: bool,
    gui_bus: Optional[GuiEventBus] = None,
):
    while True:
        await asyncio.sleep(5.0)
        log_event(
            worklog_path,
            {
                "stage": "HEARTBEAT",
                "action": "INFO",
                "download_q": int(download_queue.qsize()),
                "validate_q": int(validate_queue.qsize()),
                "encode_q": int(encode_queue.qsize()),
                "raw_budget_ok": bool(raw_budget_ok_event.is_set()),
                "paused": (not pause_event.is_set()),
            },
            quiet=quiet,
            gui_bus=gui_bus,
        )


# ============================================================
#                 FS HELPERS
# ============================================================

def remove_with_log(path: str, *, worklog_path: str, quiet: bool, ctx: Dict[str, Any], reason: str, gui_bus: Optional[GuiEventBus] = None):
    try:
        if path and os.path.exists(path):
            os.remove(path)
            log_event(worklog_path, {**ctx, "stage": "CLEANUP", "action": "DELETE", "reason": reason, "path": path}, quiet=quiet, gui_bus=gui_bus)
    except Exception as e:
        log_event(worklog_path, {**ctx, "stage": "CLEANUP", "action": "WARN", "reason": "delete_failed", "path": path, "error": str(e)}, quiet=quiet, gui_bus=gui_bus)

def replace_with_log(src: str, dst: str, *, worklog_path: str, quiet: bool, ctx: Dict[str, Any], reason: str, gui_bus: Optional[GuiEventBus] = None):
    os.replace(src, dst)
    log_event(worklog_path, {**ctx, "stage": "FS", "action": "REPLACE", "reason": reason, "src": src, "dst": dst}, quiet=quiet, gui_bus=gui_bus)

def rename_with_log(src: str, dst: str, *, worklog_path: str, quiet: bool, ctx: Dict[str, Any], reason: str, gui_bus: Optional[GuiEventBus] = None) -> str:
    try:
        if src and os.path.exists(src):
            os.replace(src, dst)
            log_event(worklog_path, {**ctx, "stage": "FS", "action": "RENAME", "reason": reason, "src": src, "dst": dst}, quiet=quiet, gui_bus=gui_bus)
            return dst
    except Exception as e:
        log_event(worklog_path, {**ctx, "stage": "FS", "action": "WARN", "reason": "rename_failed", "src": src, "dst": dst, "error": str(e)}, quiet=quiet, gui_bus=gui_bus)
    return src


# ============================================================
#                 ID / OUTPUT CHECK
# ============================================================

_ID_RE = re.compile(r"__([0-9]+)\.mp4$", re.IGNORECASE)

def extract_pexels_id_from_filename(name: str) -> Optional[int]:
    m = _ID_RE.search(os.path.basename(name))
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None

def is_output_file(path: Path) -> bool:
    n = path.name.lower()
    return n.endswith(".mp4") and (not n.startswith("raw__")) and (not n.startswith("ok_raw__"))

def scan_existing_output_ids(video_dir: str) -> set:
    ids = set()
    try:
        for p in Path(video_dir).glob("*.mp4"):
            if not is_output_file(p):
                continue
            pid = extract_pexels_id_from_filename(p.name)
            if pid is not None:
                ids.add(pid)
    except Exception:
        pass
    return ids

def output_id_exists_on_disk(video_dir: str, pid: int) -> bool:
    try:
        for p in Path(video_dir).glob(f"*__{pid}.mp4"):
            if is_output_file(p):
                return True
    except Exception:
        return False
    return False


# ============================================================
#                 WORKLOG SCAN (skip already processed IDs)
# ============================================================

def scan_processed_ids_from_worklog(worklog_path: str) -> set:
    ids = set()
    try:
        if not worklog_path or not os.path.exists(worklog_path):
            return ids
        with open(worklog_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                vid = obj.get("id")
                if vid is not None:
                    try:
                        ids.add(int(vid))
                        continue
                    except Exception:
                        pass
                for k in ("raw_path", "mp4_path", "path", "src", "dst"):
                    v = obj.get(k)
                    if isinstance(v, str):
                        pid = extract_pexels_id_from_filename(v)
                        if pid is not None:
                            ids.add(pid)
    except Exception:
        return ids
    return ids


# ============================================================
#                 UTILS
# ============================================================

def sanitize_filename(name: str, max_len: int = 150) -> str:
    name = name.strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    name = name[:max_len].rstrip(" .")
    return name or "video"

def pick_4_options(correct: str, pool: Sequence[str]) -> Tuple[List[str], int]:
    correct_u = correct.strip().upper()
    pool_u, seen = [], set()
    for x in pool:
        x = x.strip().upper()
        if x and x not in seen:
            seen.add(x)
            pool_u.append(x)
    distractors = [x for x in pool_u if x != correct_u]
    if len(distractors) < 3:
        raise ValueError("Pool opzioni insufficiente per 4 risposte.")
    opts = random.sample(distractors, 3) + [correct_u]
    random.shuffle(opts)
    return opts, opts.index(correct_u) + 1

def append_quiz_txt(path: str, q: Dict[str, Any]):
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"DOMANDA: {q['domanda']}\n")
        f.write(f"VIDEO: {q['video']}\n")
        for i, opt in enumerate(q["opzioni"], start=1):
            f.write(f"OPZIONE{i}: {opt}\n")
        f.write(f"RISPOSTA: {q['risposta']}\n")
        f.write(f"DURATA: {q['durata']}\n\n")
        f.flush()
        os.fsync(f.fileno())

def ffmpeg_path() -> Optional[str]:
    return shutil.which("ffmpeg")

def clamp(n: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, n))

def kbps_to_ffmpeg(kbps: int) -> str:
    return f"{int(kbps)}k"

def compute_target_video_kbps(*, target_mb: float, duration_s: int, audio_kbps: int = 0, container_overhead_pct: float = 3.0) -> int:
    duration_s = max(1, int(duration_s))
    target_bits = float(target_mb) * 1024.0 * 1024.0 * 8.0
    target_bits *= (1.0 - (container_overhead_pct / 100.0))
    audio_bits = float(audio_kbps) * 1000.0 * float(duration_s)
    video_bits = max(1000.0, target_bits - audio_bits)
    video_kbps = int(video_bits / float(duration_s) / 1000.0)
    return max(50, video_kbps)

def have_encoder(encoder_name: str) -> bool:
    exe = ffmpeg_path()
    if not exe:
        return False
    try:
        out = subprocess.check_output([exe, "-hide_banner", "-encoders"], stderr=subprocess.STDOUT, text=True, timeout=15)
        return encoder_name in out
    except Exception:
        return False

def bytes_to_gb(n: int) -> float:
    return float(n) / (1024.0 ** 3)

def get_raw_bytes(video_dir: str) -> int:
    total = 0
    try:
        for p in Path(video_dir).iterdir():
            if not p.is_file():
                continue
            n = p.name.lower()
            if n.startswith("raw__") or n.startswith("ok_raw__"):
                total += p.stat().st_size
    except Exception:
        return 0
    return total

def file_size_mb(path: str) -> float:
    try:
        return os.path.getsize(path) / (1024 * 1024)
    except Exception:
        return 0.0

def ensure_list_keywords(x: LabelKeywords) -> List[str]:
    if isinstance(x, list):
        return [str(s) for s in x if str(s).strip()]
    if isinstance(x, str):
        s = x.strip()
        return [s] if s else []
    return []

def pick_keyword_for_label(x: LabelKeywords) -> str:
    kws = ensure_list_keywords(x)
    if not kws:
        return ""
    return random.choice(kws)

def representative_keyword_for_label(x: LabelKeywords) -> str:
    kws = ensure_list_keywords(x)
    return kws[0] if kws else ""

def get_video_wh(path: str) -> Tuple[int, int]:
    exe = shutil.which("ffprobe")
    if not exe:
        return (0, 0)
    try:
        cmd = [
            exe, "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json",
            path,
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
        data = json.loads(out)
        streams = data.get("streams") or []
        if not streams:
            return (0, 0)
        w = int(streams[0].get("width") or 0)
        h = int(streams[0].get("height") or 0)
        return (w, h)
    except Exception:
        return (0, 0)

def trace_to_str(trace_list: List[Dict[str, Any]]) -> str:
    parts = []
    for t in trace_list or []:
        step = str(t.get("step", ""))
        ok = t.get("ok", None)
        if ok is True:
            parts.append(f"{step}:OK")
        elif ok is False:
            parts.append(f"{step}:KO")
        else:
            parts.append(step)
    return " > ".join([p for p in parts if p])

def append_decisions_csv(csv_path: str, row: Dict[str, Any]) -> None:
    import csv
    os.makedirs(os.path.dirname(os.path.abspath(csv_path)) or ".", exist_ok=True)
    new_file = not os.path.exists(csv_path)
    fieldnames = [
        "ts", "id", "template", "label", "keyword",
        "raw_path", "mp4_path",
        "w", "h", "vertical",
        "clip_ok",
        # majority vote summary
        "vote_pass", "vote_total", "vote_strong_pass", "vote_strong_total",
        # per-check results (JSON)
        "checks_json",
        "decision", "reason",
        "trace",
    ]
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        wri = csv.DictWriter(f, fieldnames=fieldnames)
        if new_file:
            wri.writeheader()
        wri.writerow({k: row.get(k, "") for k in fieldnames})


# ============================================================
#                 PEXELS
# ============================================================

def pick_pexels_mp4_link(video_obj: Dict[str, Any], *, max_width: int, min_width: int) -> Tuple[str, Dict[str, Any]]:
    files = [f for f in (video_obj.get("video_files") or []) if f.get("link") and f.get("file_type") == "video/mp4"]
    if not files:
        return "", {}
    def w(f): return int(f.get("width") or 0)
    eligible = [f for f in files if (w(f) <= int(max_width) and w(f) >= int(min_width))]
    if eligible:
        chosen = sorted(eligible, key=lambda x: w(x))[-1]
        return chosen["link"], chosen
    chosen = sorted(files, key=lambda x: w(x))[0]
    return chosen["link"], chosen

def pexels_search_videos(pexels_api_key: str, query: str, *, per_label: int = 30, min_interval: float = 1.2, timeout_s: int = 30) -> List[Dict[str, Any]]:
    if min_interval and min_interval > 0:
        time.sleep(min_interval)
    headers = {"Authorization": pexels_api_key}
    params: Dict[str, Any] = {"query": query, "per_page": int(per_label)}
    r = requests.get(PEXELS_API_URL, headers=headers, params=params, timeout=timeout_s)
    r.raise_for_status()
    return r.json().get("videos", [])


# ============================================================
#                 FRAMES / FFPROBE
# ============================================================

def pick_frame_seconds_from_duration(duration: float, *, n: int = 3) -> List[float]:
    if duration <= 0.8:
        return [0.0]
    rel = [0.2, 0.5, 0.8][:max(1, n)]
    max_ss = max(0.0, duration - 0.5)
    out = []
    for r in rel:
        out.append(max(0.0, min(duration * r, max_ss)))
    out2 = []
    for s in out:
        if not out2 or abs(out2[-1] - s) > 0.01:
            out2.append(round(s, 3))
    return out2

def extract_frame(video_path: str, out_path: str, ss: float) -> bool:
    try:
        (
            ffmpeg.input(video_path, ss=ss)
            .output(out_path, vframes=1)
            .global_args("-hide_banner", "-loglevel", "error")
            .run(capture_stdout=True, capture_stderr=True, overwrite_output=True)
        )
        return os.path.exists(out_path)
    except Exception:
        return False

def get_video_duration(path: str) -> float:
    exe = shutil.which("ffprobe")
    if not exe:
        return 0.0
    try:
        cmd = [exe, "-v", "error", "-select_streams", "v:0", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", path]
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        return float(out.strip())
    except Exception:
        return 0.0


# ============================================================
#                 DOWNLOAD
# ============================================================

async def async_download_file(session, url: str, dest: Path, sem: asyncio.Semaphore, raw_budget_ok_event: asyncio.Event, pause_event: asyncio.Event, *, worklog_path: str, ctx: Dict[str, Any], quiet: bool, gui_bus: Optional[GuiEventBus]):
    await raw_budget_ok_event.wait()
    await pause_event.wait()
    for attempt in range(1, RETRY + 1):
        async with sem:
            await raw_budget_ok_event.wait()
            await pause_event.wait()
            try:
                log_event(worklog_path, {**ctx, "stage": "DOWNLOAD", "action": "START", "attempt": attempt, "path": str(dest)}, quiet=quiet, gui_bus=gui_bus)
                async with session.get(url) as resp:
                    resp.raise_for_status()
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    async with aiofiles.open(dest, "wb") as f:
                        async for chunk in resp.content.iter_chunked(CHUNK):
                            await pause_event.wait()
                            await f.write(chunk)
                log_event(worklog_path, {**ctx, "stage": "DOWNLOAD", "action": "OK", "path": str(dest)}, quiet=quiet, gui_bus=gui_bus)
                return True
            except Exception as e:
                log_event(worklog_path, {**ctx, "stage": "DOWNLOAD", "action": "WARN", "reason": "download_error", "attempt": attempt, "path": str(dest), "error": str(e)}, quiet=quiet, gui_bus=gui_bus)
                if attempt == RETRY:
                    return False
                await asyncio.sleep(1)


# ============================================================
#                 CLIP
# ============================================================

_CLIP_MODEL = None
_CLIP_PREPROCESS = None

def _load_clip_model(device="cpu"):
    global _CLIP_MODEL, _CLIP_PREPROCESS
    if _CLIP_MODEL is None:
        _CLIP_MODEL, _CLIP_PREPROCESS = clip.load("ViT-B/32", device=device)
    return _CLIP_MODEL, _CLIP_PREPROCESS

def clip_inference_detailed(
    *,
    raw_path: str,
    keyword: str,
    candidate_keywords: List[str],
    device: str,
    threshold: float,
    min_matches: int,
    frames_dir: str,
    keep_frames: bool,
    duration: float,
    n_frames: int,
) -> Dict[str, Any]:
    model, preprocess = _load_clip_model(device)
    kw_norm = lambda s: (s or "").strip().lower()
    keyword_n = kw_norm(keyword)
    cand = [kw_norm(k) for k in (candidate_keywords or []) if kw_norm(k)]
    if keyword_n and keyword_n not in cand:
        cand.append(keyword_n)
    cand = list(dict.fromkeys(cand))

    if len(cand) < 2:
        return {"ok": False, "matches": 0, "required": min_matches, "threshold": threshold, "seconds": [], "errors": {"_": "need_at_least_2_candidate_keywords_for_clip_classification"}}

    text_tokens = clip.tokenize(cand).to(device)
    seconds = pick_frame_seconds_from_duration(duration, n=int(max(1, n_frames)))

    if keep_frames:
        os.makedirs(frames_dir, exist_ok=True)

    matches = 0
    errors: Dict[str, str] = {}

    for ss in seconds:
        frame_path = os.path.join(frames_dir, f"{Path(raw_path).name}.clip_{ss}.jpg") if keep_frames else f"{raw_path}.clip_{ss}.jpg"
        if not extract_frame(raw_path, frame_path, ss=float(ss)):
            errors[str(ss)] = "extract_fail"
            if not keep_frames:
                try:
                    os.remove(frame_path)
                except Exception:
                    pass
            continue
        try:
            image = preprocess(Image.open(frame_path)).unsqueeze(0).to(device)
            with torch.no_grad():
                logits_per_image, _ = model(image, text_tokens)
                probs = logits_per_image.softmax(dim=-1)[0]
                best_idx = int(torch.argmax(probs).item())
                best_kw = cand[best_idx]
                best_p = float(probs[best_idx].item())
                if best_kw == keyword_n and best_p >= float(threshold):
                    matches += 1
        except Exception as e:
            errors[str(ss)] = f"infer_fail: {e}"
        finally:
            if not keep_frames:
                try:
                    os.remove(frame_path)
                except Exception:
                    pass

    ok = matches >= int(min_matches)
    return {"ok": ok, "matches": matches, "required": int(min_matches), "threshold": float(threshold), "seconds": seconds, "errors": errors}

def clip_worker(args):
    raw_path, keyword, candidate_keywords, device, threshold, min_matches, frames_dir, keep_frames, duration, n_frames = args
    try:
        data = clip_inference_detailed(
            raw_path=raw_path,
            keyword=keyword,
            candidate_keywords=candidate_keywords,
            device=device,
            threshold=float(threshold),
            min_matches=int(min_matches),
            frames_dir=frames_dir,
            keep_frames=bool(keep_frames),
            duration=float(duration),
            n_frames=int(n_frames),
        )
        return (raw_path, data, None)
    except Exception as e:
        return (raw_path, None, str(e))


# ============================================================
#   NEW MODULES: shot detection, BLIP VQA, YOLO, OWLv2,
#                color analysis, photometric, ASR, OCR, tracking
#
# Design: thread-safe lazy loading via module-level globals + locks.
# All models auto-download on first use from HuggingFace Hub / ultralytics.
# All functions return {"ok": bool|None, ...} where ok=None means skipped/error.
# ============================================================

import threading as _threading

_BLIP_LOCK = _threading.Lock()
_YOLO_LOCK = _threading.Lock()
_OWLV2_LOCK = _threading.Lock()
_WHISPER_LOCK = _threading.Lock()

_BLIP_PROC = None
_BLIP_MODEL_VQA = None
_YOLO_MODEL_OBJ = None
_OWLV2_PROC = None
_OWLV2_MODEL_OBJ = None
_WHISPER_MODEL_OBJ = None


def _load_blip_vqa():
    """Lazy-load Salesforce/blip-vqa-base (~960 MB, auto-downloads from HuggingFace)."""
    global _BLIP_PROC, _BLIP_MODEL_VQA
    with _BLIP_LOCK:
        if _BLIP_PROC is None:
            from transformers import BlipProcessor, BlipForQuestionAnswering
            _BLIP_PROC = BlipProcessor.from_pretrained("Salesforce/blip-vqa-base")
            _BLIP_MODEL_VQA = BlipForQuestionAnswering.from_pretrained("Salesforce/blip-vqa-base")
            _BLIP_MODEL_VQA.eval()
    return _BLIP_PROC, _BLIP_MODEL_VQA


def _load_yolo():
    """Lazy-load YOLOv8n (~6 MB, auto-downloads from ultralytics CDN)."""
    global _YOLO_MODEL_OBJ
    with _YOLO_LOCK:
        if _YOLO_MODEL_OBJ is None:
            from ultralytics import YOLO
            _YOLO_MODEL_OBJ = YOLO("yolov8n.pt")
    return _YOLO_MODEL_OBJ


def _load_owlv2():
    """Lazy-load google/owlvit-base-patch32 (auto-downloads from HuggingFace)."""
    global _OWLV2_PROC, _OWLV2_MODEL_OBJ
    with _OWLV2_LOCK:
        if _OWLV2_PROC is None:
            from transformers import OwlViTProcessor, OwlViTForObjectDetection
            _OWLV2_PROC = OwlViTProcessor.from_pretrained("google/owlvit-base-patch32")
            _OWLV2_MODEL_OBJ = OwlViTForObjectDetection.from_pretrained("google/owlvit-base-patch32")
            _OWLV2_MODEL_OBJ.eval()
    return _OWLV2_PROC, _OWLV2_MODEL_OBJ


def _load_whisper():
    """Lazy-load faster-whisper tiny (auto-downloads, CPU int8)."""
    global _WHISPER_MODEL_OBJ
    with _WHISPER_LOCK:
        if _WHISPER_MODEL_OBJ is None:
            from faster_whisper import WhisperModel
            _WHISPER_MODEL_OBJ = WhisperModel("tiny", device="cpu", compute_type="int8")
    return _WHISPER_MODEL_OBJ


# ---- Shot detection + keyframe extraction ----

def extract_keyframes_for_validation(
    video_path: str,
    frames_base_dir: str,
    duration: float,
    n_frames: int = 5,
    *,
    keep: bool = False,
) -> Tuple[List[str], Optional[str]]:
    """
    Extract keyframes from video for all checks.
    Tries PySceneDetect first; falls back to uniform sampling.
    Returns (frame_paths, cleanup_dir).  cleanup_dir is None when keep=True.
    """
    base = Path(video_path).stem[:60]
    if keep:
        kf_dir = os.path.join(frames_base_dir, base)
        cleanup_dir: Optional[str] = None
    else:
        kf_dir = tempfile.mkdtemp(prefix=f"kf_{base[:30]}_")
        cleanup_dir = kf_dir
    os.makedirs(kf_dir, exist_ok=True)

    # Try PySceneDetect
    try:
        from scenedetect import open_video, SceneManager
        from scenedetect.detectors import ContentDetector
        video = open_video(video_path)
        sm = SceneManager()
        sm.add_detector(ContentDetector(threshold=27.0))
        sm.detect_scenes(video, show_progress=False)
        scenes = sm.get_scene_list()
        times = [float(s[0].get_seconds()) for s in scenes]
        if len(times) > n_frames:
            step = len(times) / n_frames
            times = [times[int(i * step)] for i in range(n_frames)]
        if not times:
            raise RuntimeError("no_scenes")
        frames: List[str] = []
        for i, t in enumerate(times[:n_frames]):
            fp = os.path.join(kf_dir, f"scene_{i:03d}.jpg")
            ss = float(min(t, max(0.0, duration - 0.5)))
            if extract_frame(video_path, fp, ss=ss):
                frames.append(fp)
        if frames:
            return frames, cleanup_dir
    except Exception:
        pass

    # Fallback: uniform sampling
    frames = []
    seconds = pick_frame_seconds_from_duration(duration, n=int(max(1, n_frames)))
    for i, ss in enumerate(seconds):
        fp = os.path.join(kf_dir, f"uni_{i:03d}.jpg")
        if extract_frame(video_path, fp, ss=float(ss)):
            frames.append(fp)
    return frames, cleanup_dir


# ---- BLIP VQA check ----

def _build_blip_question(concept_en: str, template_cat: str, label_it: str) -> str:
    """Build a yes/no VQA question for BLIP based on template category."""
    c = concept_en.strip()
    label = label_it.strip().upper()
    COLOR_EN: Dict[str, str] = {
        "NERO": "black", "BIANCO": "white", "ROSSO": "red", "BLU": "blue",
        "VERDE": "green", "GIALLO": "yellow", "ARANCIONE": "orange",
        "VIOLA": "purple", "ROSA": "pink", "GRIGIO": "gray",
    }
    if template_cat == "colors":
        en_color = COLOR_EN.get(label, c)
        return f"Is the predominant color {en_color}?"
    if template_cat == "lighting":
        return f"Is the scene lit by {c}?"
    if template_cat in ("actions", "vlm"):
        return f"Are there {c} in this image?"
    return f"Is there {c} in this image?"


def check_blip_vqa(
    frame_paths: List[str],
    question: str,
    device: str = "cpu",
) -> Dict[str, Any]:
    """
    Run BLIP VQA (yes/no) on keyframes.
    Returns ok=True if majority of frames answer 'yes'.
    Model: Salesforce/blip-vqa-base — auto-downloads on first call.
    """
    if not frame_paths:
        return {"ok": None, "error": "no_frames"}
    try:
        proc, model = _load_blip_vqa()
        dev = torch.device(device if torch.cuda.is_available() or device == "cpu" else "cpu")
        model = model.to(dev)
        yes_count = 0
        answers: List[str] = []
        for fp in frame_paths:
            try:
                img = Image.open(fp).convert("RGB")
                inputs = proc(images=img, text=question, return_tensors="pt").to(dev)
                with torch.no_grad():
                    out = model.generate(**inputs, max_new_tokens=10)
                answer = proc.decode(out[0], skip_special_tokens=True).strip().lower()
                answers.append(answer)
                if "yes" in answer:
                    yes_count += 1
            except Exception:
                continue
        total = len(answers)
        ok = (total > 0) and (yes_count > total / 2)
        return {"ok": ok, "yes_count": yes_count, "total": total,
                "sample_answers": answers[:3], "question": question}
    except Exception as e:
        return {"ok": None, "error": str(e)}


# ---- YOLO detection check ----

def get_yolo_classes_for_label(label_it: str) -> List[str]:
    """Return COCO class names for an Italian label, [] if not mappable."""
    return YOLO_LABEL_MAP.get(label_it.upper(), [])


def check_yolo_on_keyframes(
    frame_paths: List[str],
    target_classes: List[str],
    confidence: float = 0.30,
) -> Dict[str, Any]:
    """
    Run YOLOv8n on keyframes, check if any target class is detected.
    Model: yolov8n.pt (~6 MB) — auto-downloads on first call.
    """
    if not frame_paths:
        return {"ok": None, "error": "no_frames"}
    if not target_classes:
        return {"ok": None, "error": "no_yolo_classes_for_label"}
    try:
        model = _load_yolo()
        tc_lower = [c.lower() for c in target_classes]
        found: List[str] = []
        for fp in frame_paths:
            try:
                results = model.predict(fp, conf=confidence, verbose=False)
                for r in results:
                    if r.boxes is None:
                        continue
                    for cls_id in r.boxes.cls.tolist():
                        cls_name = model.names[int(cls_id)].lower()
                        if cls_name in tc_lower:
                            found.append(cls_name)
            except Exception:
                continue
        ok = len(found) > 0
        return {"ok": ok, "found_classes": found[:10], "target_classes": target_classes}
    except Exception as e:
        return {"ok": None, "error": str(e)}


# ---- OWLv2 (OWLViT) open-vocabulary grounding ----

def check_owlv2_grounding(
    frame_paths: List[str],
    concept_en: str,
    device: str = "cpu",
    score_threshold: float = 0.10,
) -> Dict[str, Any]:
    """
    Run OWLViT open-vocabulary detection on keyframes.
    Model: google/owlvit-base-patch32 — auto-downloads on first call.
    """
    if not frame_paths:
        return {"ok": None, "error": "no_frames"}
    try:
        proc, model = _load_owlv2()
        dev = torch.device(device if torch.cuda.is_available() or device == "cpu" else "cpu")
        model = model.to(dev)
        texts = [[f"a photo of {concept_en}"]]
        best_score = 0.0
        for fp in frame_paths:
            try:
                img = Image.open(fp).convert("RGB")
                inputs = proc(text=texts, images=img, return_tensors="pt").to(dev)
                with torch.no_grad():
                    outputs = model(**inputs)
                # logits shape: (1, num_patches, num_queries)
                logits = outputs.logits[0]  # (num_patches, 1)
                scores = torch.sigmoid(logits[:, 0])
                frame_best = float(scores.max().item())
                best_score = max(best_score, frame_best)
            except Exception:
                continue
        ok = best_score >= score_threshold
        return {"ok": ok, "best_score": round(best_score, 4), "threshold": score_threshold}
    except Exception as e:
        return {"ok": None, "error": str(e)}


# ---- Color analysis ----

def check_color_analysis(
    frame_paths: List[str],
    label_it: str,
) -> Dict[str, Any]:
    """
    Analyze dominant color in keyframes using pixel statistics (numpy + PIL).
    No extra dependencies beyond PIL and numpy (already required via torch).
    """
    if not frame_paths:
        return {"ok": None, "error": "no_frames"}
    config = COLOR_ANALYSIS_CONFIG.get(label_it.upper())
    if config is None:
        return {"ok": None, "error": f"no_color_config_for_{label_it}"}
    try:
        import numpy as np
        ok_frames = 0
        total_frames = 0
        for fp in frame_paths:
            try:
                img = Image.open(fp).convert("RGB")
                arr = np.array(img, dtype=np.float32)
                h, w = arr.shape[:2]
                total_px = h * w
                ctype = config["type"]
                thr = float(config.get("threshold", 0.15))
                ok_frame = False

                if ctype == "brightness":
                    gray = np.mean(arr, axis=2)
                    pct = float(np.sum(gray < config["max_v"]) / total_px)
                    ok_frame = pct >= thr

                elif ctype == "brightness_high":
                    gray = np.mean(arr, axis=2)
                    diff = np.max(arr, axis=2) - np.min(arr, axis=2)
                    mask = (gray > config["min_v"]) & (diff < config["min_s_inv"])
                    pct = float(np.sum(mask) / total_px)
                    ok_frame = pct >= thr

                elif ctype == "gray":
                    diff = np.max(arr, axis=2) - np.min(arr, axis=2)
                    gray = np.mean(arr, axis=2)
                    mask = (diff < config["max_s"]) & (gray > config["min_v"]) & (gray < config["max_v"])
                    pct = float(np.sum(mask) / total_px)
                    ok_frame = pct >= thr

                else:
                    # HSV-based (pure numpy, no cv2 dependency)
                    arr_n = arr / 255.0
                    maxc = np.max(arr_n, axis=2)
                    minc = np.min(arr_n, axis=2)
                    diff = maxc - minc
                    r, g, b = arr_n[:, :, 0], arr_n[:, :, 1], arr_n[:, :, 2]
                    hue = np.zeros((h, w), dtype=np.float32)
                    mr = (maxc == r) & (diff > 0)
                    mg = (maxc == g) & (diff > 0)
                    mb = (maxc == b) & (diff > 0)
                    hue[mr] = (60.0 * ((g[mr] - b[mr]) / diff[mr]) % 360.0) / 2.0
                    hue[mg] = (60.0 * ((b[mg] - r[mg]) / diff[mg] + 2.0) % 360.0) / 2.0
                    hue[mb] = (60.0 * ((r[mb] - g[mb]) / diff[mb] + 4.0) % 360.0) / 2.0
                    sat = np.where(maxc > 0, diff / (maxc + 1e-7) * 255.0, 0.0)
                    val = maxc * 255.0

                    def _hsv_mask(lo, hi):
                        return (
                            (hue >= lo[0]) & (hue <= hi[0]) &
                            (sat >= lo[1]) & (sat <= hi[1]) &
                            (val >= lo[2]) & (val <= hi[2])
                        )

                    if ctype == "hsv":
                        lo, hi = config["range"]
                        pct = float(np.sum(_hsv_mask(lo, hi)) / total_px)
                        ok_frame = pct >= thr
                    elif ctype == "hsv_double":
                        lo1, hi1 = config["range1"]
                        lo2, hi2 = config["range2"]
                        pct = float(np.sum(_hsv_mask(lo1, hi1) | _hsv_mask(lo2, hi2)) / total_px)
                        ok_frame = pct >= thr

                if ok_frame:
                    ok_frames += 1
                total_frames += 1
            except Exception:
                continue
        if total_frames == 0:
            return {"ok": None, "error": "all_frames_failed"}
        ok = ok_frames > total_frames / 2
        return {"ok": ok, "ok_frames": ok_frames, "total_frames": total_frames}
    except Exception as e:
        return {"ok": None, "error": str(e)}


# ---- Photometric analysis (lighting templates) ----

def check_photometric(
    frame_paths: List[str],
    label_it: str,
) -> Dict[str, Any]:
    """
    Photometric analysis for lighting templates (luminance, saturation, warm/cool colors).
    No extra dependencies beyond PIL and numpy.
    """
    if not frame_paths:
        return {"ok": None, "error": "no_frames"}
    rule_config = PHOTOMETRIC_CONFIG.get(label_it.upper())
    if rule_config is None:
        return {"ok": None, "error": f"no_photometric_rule_for_{label_it}"}
    try:
        import numpy as np
        ok_frames = 0
        total_frames = 0
        for fp in frame_paths:
            try:
                img = Image.open(fp).convert("RGB")
                arr = np.array(img, dtype=np.float32)
                gray = np.mean(arr, axis=2)
                mean_br = float(np.mean(gray))
                std_br = float(np.std(gray))
                rule = rule_config["rule"]
                ok_frame = False

                if rule == "dark":
                    ok_frame = mean_br < rule_config["max_mean_brightness"]
                elif rule == "warm_colors":
                    r_mean = float(np.mean(arr[:, :, 0]))
                    b_mean = float(np.mean(arr[:, :, 2]))
                    warm = max(0.0, (r_mean - b_mean) / 255.0)
                    ok_frame = warm >= rule_config["warm_ratio"]
                elif rule == "cool_colors":
                    r_mean = float(np.mean(arr[:, :, 0]))
                    b_mean = float(np.mean(arr[:, :, 2]))
                    cool = max(0.0, (b_mean - r_mean) / 255.0)
                    ok_frame = cool >= rule_config["cool_ratio"]
                elif rule == "saturated":
                    maxc = np.max(arr, axis=2)
                    minc = np.min(arr, axis=2)
                    sat = np.where(maxc > 0, (maxc - minc) / (maxc + 1e-7), 0.0)
                    sat_ratio = float(np.mean(sat > 0.5))
                    ok_frame = sat_ratio >= rule_config["sat_ratio"]
                elif rule == "bright_contrasty":
                    ok_frame = (mean_br >= rule_config.get("min_mean_brightness", 100)
                                and std_br >= rule_config.get("min_contrast", 20))
                elif rule == "contrasty":
                    ok_frame = std_br >= rule_config.get("min_contrast", 20)
                elif rule == "silhouette":
                    dark_ratio = float(np.sum(gray < 50) / gray.size)
                    ok_frame = dark_ratio >= rule_config.get("silhouette_ratio", 0.15)

                if ok_frame:
                    ok_frames += 1
                total_frames += 1
            except Exception:
                continue
        if total_frames == 0:
            return {"ok": None, "error": "all_frames_failed"}
        ok = ok_frames > total_frames / 2
        return {"ok": ok, "ok_frames": ok_frames, "total_frames": total_frames}
    except Exception as e:
        return {"ok": None, "error": str(e)}


# ---- ASR with faster-whisper ----

def check_asr_transcript(
    video_path: str,
    concept_en: str,
) -> Dict[str, Any]:
    """
    Run faster-whisper ASR on video audio, check if concept appears in transcript.
    Model: whisper tiny (CPU int8) — auto-downloads on first call.
    Enable via --enable-asr (disabled by default).
    """
    try:
        model = _load_whisper()
        segments, _ = model.transcribe(video_path, language="en", task="transcribe")
        text_parts: List[str] = []
        timestamps: List[Dict[str, Any]] = []
        for seg in segments:
            text_parts.append(seg.text)
            timestamps.append({"start": round(seg.start, 1), "end": round(seg.end, 1), "text": seg.text})
        full_text = " ".join(text_parts).lower()
        concept_in_text = concept_en.lower() in full_text
        return {
            "ok": True,  # ASR is a support check — not a hard gate
            "has_concept": concept_in_text,
            "text_snippet": full_text[:200],
            "concept": concept_en,
            "timestamps": timestamps[:5],
        }
    except Exception as e:
        return {"ok": None, "error": str(e)}


# ---- OCR on keyframes ----

def check_ocr_keyframes(
    frame_paths: List[str],
    concept_en: str,
) -> Dict[str, Any]:
    """
    Run pytesseract OCR on keyframes.
    Requires: pip install pytesseract AND system-level tesseract-ocr binary.
    Enable via --enable-ocr (disabled by default).
    """
    if not frame_paths:
        return {"ok": None, "error": "no_frames"}
    try:
        import pytesseract
        texts: List[str] = []
        for fp in frame_paths:
            try:
                img = Image.open(fp)
                text = pytesseract.image_to_string(img, lang="eng+ita", config="--psm 3")
                texts.append(text.strip())
            except Exception:
                continue
        combined = " ".join(texts).lower()
        concept_in_text = concept_en.lower() in combined
        return {
            "ok": True,  # OCR is a support check — not a hard gate
            "has_concept": concept_in_text,
            "combined_text": combined[:200],
        }
    except Exception as e:
        return {"ok": None, "error": str(e)}


# ---- IOU tracking ----

def _compute_iou(
    box1: Tuple[float, float, float, float],
    box2: Tuple[float, float, float, float],
) -> float:
    """Compute IOU between two boxes (x1, y1, x2, y2) in normalised [0,1] coords."""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area1 = max(0.0, box1[2] - box1[0]) * max(0.0, box1[3] - box1[1])
    area2 = max(0.0, box2[2] - box2[0]) * max(0.0, box2[3] - box2[1])
    union = area1 + area2 - inter
    return inter / union if union > 0 else 0.0


def check_iou_tracking(
    frame_paths: List[str],
    label_it: str,
    device: str = "cpu",
    iou_threshold: float = 0.30,
) -> Dict[str, Any]:
    """
    Simple IOU-based consistency check: verifies that detected objects appear
    in at least 2 consecutive keyframes (using YOLO detections).
    """
    if len(frame_paths) < 2:
        return {"ok": None, "error": "need_at_least_2_frames"}
    target_classes = get_yolo_classes_for_label(label_it)
    if not target_classes:
        return {"ok": None, "error": "no_yolo_classes_for_tracking"}
    try:
        model = _load_yolo()
        tc_lower = [c.lower() for c in target_classes]
        all_boxes: List[List[Tuple[float, float, float, float]]] = []
        for fp in frame_paths:
            frame_boxes: List[Tuple[float, float, float, float]] = []
            try:
                results = model.predict(fp, conf=0.25, verbose=False)
                for r in results:
                    if r.boxes is None:
                        continue
                    for cls_id, box in zip(r.boxes.cls.tolist(), r.boxes.xyxyn.tolist()):
                        if model.names[int(cls_id)].lower() in tc_lower:
                            frame_boxes.append((float(box[0]), float(box[1]), float(box[2]), float(box[3])))
            except Exception:
                pass
            all_boxes.append(frame_boxes)
        tracked = False
        for i in range(len(all_boxes) - 1):
            for b1 in all_boxes[i]:
                for b2 in all_boxes[i + 1]:
                    if _compute_iou(b1, b2) >= iou_threshold:
                        tracked = True
                        break
                if tracked:
                    break
            if tracked:
                break
        frames_with_det = sum(1 for bx in all_boxes if bx)
        return {"ok": tracked, "frames_with_detections": frames_with_det}
    except Exception as e:
        return {"ok": None, "error": str(e)}


# ---- Majority vote gate ----

def majority_vote_gate(
    clip_ok: bool,
    extra_results: Dict[str, Dict[str, Any]],
    template_cat: str,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Apply majority vote across all check results.

    Returns (verdict, reason, details).

    Rules:
    - Only count checks where ok is not None (non-errored)
    - "Strong" checks must have at least 1 passing
    - ACCEPT if pass_count > total/2  AND  strong_pass >= 1 (or no strong applicable)

    Strong checks by template category:
      objects  -> CLIP, YOLO, OWLv2
      colors   -> CLIP, COLOR
      lighting -> CLIP, PHOTO
      actions  -> CLIP, BLIP
      vlm      -> CLIP, BLIP
      mixed    -> CLIP, BLIP
    """
    STRONG_BY_CAT: Dict[str, set] = {
        "objects": {"CLIP", "YOLO", "OWLv2"},
        "colors": {"CLIP", "COLOR"},
        "lighting": {"CLIP", "PHOTO"},
        "actions": {"CLIP", "BLIP"},
        "vlm": {"CLIP", "BLIP"},
        "mixed": {"CLIP", "BLIP"},
    }
    strong_set = STRONG_BY_CAT.get(template_cat, {"CLIP"})

    all_checks: List[Tuple[str, bool, bool]] = []  # (name, ok, is_strong)
    all_checks.append(("CLIP", clip_ok, "CLIP" in strong_set))

    for chk_name, res in extra_results.items():
        ok_val = res.get("ok")
        if ok_val is None:
            continue
        is_strong = chk_name in strong_set
        all_checks.append((chk_name, bool(ok_val), is_strong))

    pass_count = sum(1 for _, ok, _ in all_checks if ok)
    fail_count = sum(1 for _, ok, _ in all_checks if not ok)
    total = len(all_checks)
    strong_pass = sum(1 for _, ok, is_s in all_checks if ok and is_s)
    strong_applicable = sum(1 for _, _, is_s in all_checks if is_s)

    majority_ok = (total == 0) or (pass_count > total / 2)
    strong_ok = (strong_applicable == 0) or (strong_pass >= 1)
    verdict = majority_ok and strong_ok

    if not majority_ok:
        reason = f"majority_fail({pass_count}/{total})"
    elif not strong_ok:
        reason = f"no_strong_passed(strong_pass={strong_pass}/{strong_applicable})"
    else:
        reason = f"majority_ok({pass_count}/{total},strong={strong_pass}/{strong_applicable})"

    details = {
        "pass_count": pass_count,
        "fail_count": fail_count,
        "total": total,
        "strong_pass": strong_pass,
        "strong_applicable": strong_applicable,
        "checks": {n: ok for n, ok, _ in all_checks},
    }
    return verdict, reason, details

def cut_and_strip_audio_copy(src_path: str, dst_path: str, *, seconds: int, ffmpeg_timeout: int):
    exe = ffmpeg_path()
    if not exe:
        raise RuntimeError("ffmpeg non trovato nel PATH.")
    cmd = [exe, "-y", "-hide_banner", "-loglevel", "error",
           "-i", src_path, "-t", str(int(seconds)),
           "-map", "0:v:0?", "-an", "-sn", "-dn",
           "-c:v", "copy", "-movflags", "+faststart", dst_path]
    subprocess.run(cmd, check=True, timeout=ffmpeg_timeout)

def encode_hevc_target_mb_30s(src_path: str, dst_path: str, *, target_mb: float, preset: str, hevc_tag: str, ffmpeg_timeout: int):
    exe = ffmpeg_path()
    if not exe:
        raise RuntimeError("ffmpeg non trovato nel PATH.")
    video_kbps = compute_target_video_kbps(target_mb=float(target_mb), duration_s=30, audio_kbps=0)
    video_kbps = int(clamp(video_kbps, 200, 8000))
    buf_kbps = int(max(200, video_kbps * BUF_SIZE_MULT))
    bitrate = kbps_to_ffmpeg(video_kbps)
    cmd = [exe, "-y", "-hide_banner", "-loglevel", "error",
           "-stream_loop", "-1", "-i", src_path, "-t", "30",
           "-map", "0:v:0?", "-an", "-sn", "-dn",
           "-c:v", "libx265", "-preset", preset, "-tag:v", hevc_tag,
           "-b:v", bitrate, "-maxrate", bitrate, "-bufsize", kbps_to_ffmpeg(buf_kbps),
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", dst_path]
    subprocess.run(cmd, check=True, timeout=ffmpeg_timeout)

def ffmpeg_worker(args):
    mode = args[0]
    try:
        if mode == "copy_cut30":
            _, src, dst, timeout = args
            cut_and_strip_audio_copy(src, dst, seconds=30, ffmpeg_timeout=int(timeout))
            return (dst, True, None)
        if mode == "encode_hevc_target_mb_30s":
            _, src, dst, timeout, target_mb, preset, hevc_tag = args
            encode_hevc_target_mb_30s(src, dst, target_mb=float(target_mb), preset=str(preset), hevc_tag=str(hevc_tag), ffmpeg_timeout=int(timeout))
            return (dst, True, None)
        return (args[2], False, f"unknown_mode: {mode}")
    except Exception as e:
        return (args[2], False, str(e))


# ============================================================
#                 RAW budget monitor
# ============================================================

async def raw_budget_monitor(*, video_dir: str, cap_gb: float, resume_ratio: float, poll_s: float, raw_budget_ok_event: asyncio.Event, worklog_path: str, quiet: bool, gui_bus: Optional[GuiEventBus]):
    cap_bytes = int(float(cap_gb) * (1024 ** 3))
    resume_bytes = int(float(cap_gb) * float(resume_ratio) * (1024 ** 3))
    raw_budget_ok_event.set()
    while True:
        await asyncio.sleep(max(0.5, float(poll_s)))
        raw_bytes = get_raw_bytes(video_dir)
        if raw_budget_ok_event.is_set():
            if raw_bytes >= cap_bytes:
                raw_budget_ok_event.clear()
                log_event(worklog_path, {"stage": "RAW_BUDGET", "action": "PAUSE", "raw_gb": round(bytes_to_gb(raw_bytes), 3), "cap_gb": cap_gb}, quiet=quiet, gui_bus=gui_bus)
        else:
            if raw_bytes <= resume_bytes:
                raw_budget_ok_event.set()
                log_event(worklog_path, {"stage": "RAW_BUDGET", "action": "RESUME", "raw_gb": round(bytes_to_gb(raw_bytes), 3), "resume_gb": round(bytes_to_gb(resume_bytes), 3)}, quiet=quiet, gui_bus=gui_bus)


# ============================================================
#                 Candidate preparation
# ============================================================

def prepare_candidates(
    videos,
    tname: str,
    correct: str,
    keyword: str,
    video_dir: str,
    max_attempts: int,
    used_output_ids: set,
    processed_ids: set,
    *,
    pexels_max_width: int,
    pexels_min_width: int,
    pexels_min_duration_s: int,
    worklog_path: str,
    quiet: bool,
    gui_bus: Optional[GuiEventBus],
):
    candidates = []
    attempts = 0

    for v in videos:
        if attempts >= max_attempts:
            break
        v_id = v.get("id")
        if v_id is None:
            continue
        try:
            v_id_int = int(v_id)
        except Exception:
            continue

        if v_id_int in processed_ids:
            continue
        if v_id_int in used_output_ids:
            continue
        if output_id_exists_on_disk(video_dir, v_id_int):
            used_output_ids.add(v_id_int)
            continue

        v_dur = v.get("duration")
        if v_dur is not None:
            try:
                if float(v_dur) < float(pexels_min_duration_s):
                    continue
            except Exception:
                pass

        base = sanitize_filename(f"{tname}__{correct}__{v_id_int}.mp4")
        raw_path = os.path.join(video_dir, f"RAW__{base}")
        mp4_path = os.path.join(video_dir, base)

        if os.path.exists(mp4_path):
            used_output_ids.add(v_id_int)
            continue

        video_url = pick_pexels_mp4_link(v, max_width=pexels_max_width, min_width=pexels_min_width)[0]
        if not video_url:
            continue

        attempts += 1
        candidates.append({
            "id": v_id_int,
            "video_url": video_url,
            "raw_path": raw_path,
            "mp4_path": mp4_path,
            "keyword": keyword,
            "label": correct,
            "template": tname,
        })

    log_event(worklog_path, {"stage": "CANDIDATES", "action": "OK", "template": tname, "label": correct, "keyword": keyword, "candidate_count": len(candidates), "min_duration": pexels_min_duration_s}, quiet=quiet, gui_bus=gui_bus)
    return candidates


# ============================================================
#                 WORKERS (NO BATCH)
# ============================================================

async def download_worker(
    name: str,
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    raw_budget_ok_event: asyncio.Event,
    pause_event: asyncio.Event,
    download_queue: asyncio.Queue,
    validate_queue: asyncio.Queue,
    *,
    worklog_path: str,
    quiet: bool,
    processed_ids: set,
    stats: PipelineStats,
    gui_bus: Optional[GuiEventBus],
):
    while True:
        c = await download_queue.get()
        if c is None:
            download_queue.task_done()
            break

        await pause_event.wait()

        ctx = {"worker": name, "id": c["id"], "template": c["template"], "label": c["label"], "keyword": c["keyword"], "raw_path": c["raw_path"], "mp4_path": c["mp4_path"]}
        pid = int(c["id"])

        if pid in processed_ids:
            log_event(worklog_path, {**ctx, "stage": "DOWNLOAD", "action": "SKIP", "reason": "id_already_processed_in_worklog"}, quiet=quiet, gui_bus=gui_bus)
            download_queue.task_done()
            continue
        if output_id_exists_on_disk(os.path.dirname(c["mp4_path"]), pid):
            log_event(worklog_path, {**ctx, "stage": "DOWNLOAD", "action": "SKIP", "reason": "output_already_exists_for_id"}, quiet=quiet, gui_bus=gui_bus)
            processed_ids.add(pid)
            download_queue.task_done()
            continue

        ok = await async_download_file(session, c["video_url"], Path(c["raw_path"]), sem, raw_budget_ok_event, pause_event, worklog_path=worklog_path, ctx=ctx, quiet=quiet, gui_bus=gui_bus)
        processed_ids.add(pid)

        if ok:
            c["trace"] = []
            stats.downloads_ok += 1
            await validate_queue.put(c)
        else:
            stats.downloads_fail += 1
            remove_with_log(c["raw_path"], worklog_path=worklog_path, quiet=quiet, ctx=ctx, reason="delete_raw_download_failed", gui_bus=gui_bus)
            stats.final_fail += 1
            log_event(worklog_path, {**ctx, "stage": "DECISION", "action": "REJECT", "reason": "download_failed", "trace": c.get("trace", [])}, quiet=quiet, gui_bus=gui_bus)
            log_event(worklog_path, {**ctx, "stage": "FINAL", "action": "FAIL", "reason": "download_failed"}, quiet=quiet, gui_bus=gui_bus)

        download_queue.task_done()


async def validate_worker(
    name: str,
    validate_queue: asyncio.Queue,
    encode_queue: asyncio.Queue,
    *,
    clip_pool: ProcessPoolExecutor,
    extra_pool: ThreadPoolExecutor,
    device: str,
    clip_threshold: float,
    clip_min_matches: int,
    clip_frames: int,
    frames_dir: str,
    keep_frames: bool,
    enable_blip: bool,
    enable_yolo: bool,
    enable_grounding: bool,
    enable_asr: bool,
    enable_ocr: bool,
    enable_tracking: bool,
    yolo_conf: float,
    owlv2_thresh: float,
    worklog_path: str,
    quiet: bool,
    stats: PipelineStats,
    gui_bus: Optional[GuiEventBus],
    decisions_csv: str,
):
    loop = asyncio.get_running_loop()
    while True:
        c = await validate_queue.get()
        if c is None:
            validate_queue.task_done()
            break

        ctx = {
            "worker": name, "id": c["id"], "template": c["template"],
            "label": c["label"], "keyword": c["keyword"],
            "raw_path": c["raw_path"], "mp4_path": c["mp4_path"],
        }

        def trace(step: str, **data):
            c.setdefault("trace", [])
            c["trace"].append({"step": step, **data})
            log_event(worklog_path, {**ctx, "stage": "TRACE", "action": step, **data}, quiet=quiet, gui_bus=gui_bus)

        def write_decision(
            *,
            decision: str,
            reason: str,
            w: int,
            h: int,
            vertical: Optional[bool],
            clip_ok: Optional[bool],
            vote_details: Optional[Dict[str, Any]] = None,
            extra_res: Optional[Dict[str, Dict[str, Any]]] = None,
        ):
            vd = vote_details or {}
            row: Dict[str, Any] = {
                "ts": now_iso(),
                "id": c.get("id"),
                "template": c.get("template"),
                "label": c.get("label"),
                "keyword": c.get("keyword"),
                "raw_path": c.get("raw_path"),
                "mp4_path": c.get("mp4_path"),
                "w": w,
                "h": h,
                "vertical": vertical,
                "clip_ok": clip_ok,
                "vote_pass": vd.get("pass_count", ""),
                "vote_total": vd.get("total", ""),
                "vote_strong_pass": vd.get("strong_pass", ""),
                "vote_strong_total": vd.get("strong_applicable", ""),
                "checks_json": json.dumps(
                    {k: v.get("ok") for k, v in (extra_res or {}).items()},
                    ensure_ascii=False,
                ),
                "decision": decision,
                "reason": reason,
                "trace": trace_to_str(c.get("trace", [])),
            }
            append_decisions_csv(decisions_csv, row)

        kf_cleanup_dir: Optional[str] = None
        keyframes: List[str] = []

        try:
            if not os.path.exists(c["raw_path"]):
                stats.final_fail += 1
                log_event(worklog_path, {**ctx, "stage": "DECISION", "action": "REJECT", "reason": "raw_missing", "trace": c.get("trace", [])}, quiet=quiet, gui_bus=gui_bus)
                write_decision(decision="REJECT", reason="raw_missing", w=0, h=0, vertical=None, clip_ok=None)
                validate_queue.task_done()
                continue

            # ---- 1. ORIENTATION gate (hard: vertical rejected immediately) ----
            w, h = get_video_wh(c["raw_path"])
            vertical: Optional[bool] = None
            if w > 0 and h > 0:
                vertical = (h > w)
            trace("ORIENTATION", w=w, h=h, vertical=vertical)

            if vertical is True:
                remove_with_log(c["raw_path"], worklog_path=worklog_path, quiet=quiet, ctx=ctx, reason="delete_raw_vertical", gui_bus=gui_bus)
                stats.final_fail += 1
                log_event(worklog_path, {**ctx, "stage": "DECISION", "action": "REJECT", "reason": "vertical_video", "w": w, "h": h, "trace": c.get("trace", [])}, quiet=quiet, gui_bus=gui_bus)
                write_decision(decision="REJECT", reason="vertical_video", w=w, h=h, vertical=vertical, clip_ok=None)
                validate_queue.task_done()
                continue

            duration = get_video_duration(c["raw_path"])
            c["duration"] = duration
            log_event(worklog_path, {**ctx, "stage": "FFPROBE", "action": "OK", "duration": duration}, quiet=quiet, gui_bus=gui_bus)

            # ---- 2. Extract keyframes (shot detection or uniform) ----
            n_kf = max(clip_frames, 4)
            raw_path_snap = c["raw_path"]
            n_kf_snap = n_kf
            dur_snap = duration
            kf_result = await loop.run_in_executor(
                extra_pool,
                lambda: extract_keyframes_for_validation(
                    raw_path_snap, frames_dir, dur_snap,
                    n_frames=n_kf_snap, keep=keep_frames,
                ),
            )
            keyframes, kf_cleanup_dir = kf_result
            log_event(worklog_path, {**ctx, "stage": "KEYFRAMES", "action": "OK", "count": len(keyframes)}, quiet=quiet, gui_bus=gui_bus)

            # ---- 3. CLIP check ----
            rep: List[str] = []
            labels = (TEMPLATES.get(c["template"]) or {}).get("labels") or {}
            for _, kw in labels.items():
                rk = representative_keyword_for_label(kw)
                if rk:
                    rep.append(rk)
            rep.append(c["keyword"])

            _, clip_data, clip_err = await loop.run_in_executor(
                None,
                lambda: clip_pool.submit(
                    clip_worker,
                    (c["raw_path"], c["keyword"], rep, device,
                     clip_threshold, clip_min_matches, frames_dir,
                     keep_frames, duration, clip_frames),
                ).result(),
            )
            clip_ok = bool(clip_data and clip_data.get("ok", False)) and (clip_err is None)
            trace(
                "CLIP",
                ok=clip_ok,
                matches=(clip_data or {}).get("matches"),
                required=(clip_data or {}).get("required"),
                threshold=clip_threshold,
            )

            # ---- 4. Extra checks (run concurrently in thread pool) ----
            tname = c["template"]
            label_it: str = c["label"]
            keyword_en: str = c["keyword"]
            template_cat = TEMPLATE_CATEGORY.get(tname, "mixed")

            # Snapshot values for lambdas (avoid late-binding closures)
            _kf = list(keyframes)
            _label = str(label_it)
            _concept = str(keyword_en)
            _dev = str(device)
            _yc = float(yolo_conf)
            _ot = float(owlv2_thresh)
            _rp = str(c["raw_path"])
            _tc = template_cat

            extra_futures: Dict[str, "asyncio.Future[Dict[str, Any]]"] = {}

            if enable_yolo and _tc in ("objects",):
                yolo_cls = get_yolo_classes_for_label(_label)
                if yolo_cls and _kf:
                    _cls = list(yolo_cls)
                    extra_futures["YOLO"] = loop.run_in_executor(
                        extra_pool, lambda: check_yolo_on_keyframes(_kf, _cls, _yc)
                    )

            if enable_blip and _kf:
                _q = _build_blip_question(_concept, _tc, _label)
                extra_futures["BLIP"] = loop.run_in_executor(
                    extra_pool, lambda: check_blip_vqa(_kf, _q, _dev)
                )

            if enable_grounding and _tc in ("objects", "actions") and _kf:
                extra_futures["OWLv2"] = loop.run_in_executor(
                    extra_pool, lambda: check_owlv2_grounding(_kf, _concept, _dev, _ot)
                )

            if _tc == "colors" and _kf:
                extra_futures["COLOR"] = loop.run_in_executor(
                    extra_pool, lambda: check_color_analysis(_kf, _label)
                )

            if _tc == "lighting" and _kf:
                extra_futures["PHOTO"] = loop.run_in_executor(
                    extra_pool, lambda: check_photometric(_kf, _label)
                )

            if enable_asr:
                extra_futures["ASR"] = loop.run_in_executor(
                    extra_pool, lambda: check_asr_transcript(_rp, _concept)
                )

            if enable_ocr and _kf:
                extra_futures["OCR"] = loop.run_in_executor(
                    extra_pool, lambda: check_ocr_keyframes(_kf, _concept)
                )

            if enable_tracking and len(_kf) >= 2 and _tc in ("objects",):
                extra_futures["TRACK"] = loop.run_in_executor(
                    extra_pool, lambda: check_iou_tracking(_kf, _label, _dev)
                )

            extra_results: Dict[str, Dict[str, Any]] = {}
            for chk_name, fut in extra_futures.items():
                try:
                    result = await fut
                    extra_results[chk_name] = result
                    safe = {k: v for k, v in result.items()
                            if k not in ("ok",) and not isinstance(v, (list, dict))}
                    trace(chk_name, ok=result.get("ok"), **safe)
                except Exception as ex:
                    extra_results[chk_name] = {"ok": None, "error": str(ex)}
                    trace(chk_name, ok=None, error=str(ex))

            # ---- 5. Majority vote ----
            verdict, vote_reason, vote_details = majority_vote_gate(
                clip_ok, extra_results, template_cat
            )

            if not verdict:
                stats.clip_fail += 1
                log_event(
                    worklog_path,
                    {**ctx, "stage": "DECISION", "action": "REJECT",
                     "reason": vote_reason, "vote": vote_details,
                     "trace": c.get("trace", [])},
                    quiet=quiet, gui_bus=gui_bus,
                )
                remove_with_log(
                    c["raw_path"], worklog_path=worklog_path,
                    quiet=quiet, ctx=ctx,
                    reason="delete_raw_majority_failed", gui_bus=gui_bus,
                )
                stats.final_fail += 1
                write_decision(
                    decision="REJECT", reason=vote_reason,
                    w=w, h=h, vertical=vertical, clip_ok=clip_ok,
                    vote_details=vote_details, extra_res=extra_results,
                )
                validate_queue.task_done()
                continue

            stats.clip_ok += 1
            log_event(
                worklog_path,
                {**ctx, "stage": "VOTE", "action": "OK",
                 "reason": vote_reason, "details": vote_details},
                quiet=quiet, gui_bus=gui_bus,
            )

            raw_path = c["raw_path"]
            ok_name = os.path.basename(raw_path)
            if not ok_name.startswith("ok_"):
                ok_name = "ok_" + ok_name
            ok_path = os.path.join(os.path.dirname(raw_path), ok_name)
            c["raw_path"] = rename_with_log(
                raw_path, ok_path,
                worklog_path=worklog_path, quiet=quiet, ctx=ctx,
                reason="mark_raw_validated", gui_bus=gui_bus,
            )

            log_event(
                worklog_path,
                {**ctx, "stage": "DECISION", "action": "ACCEPT",
                 "reason": vote_reason, "trace": c.get("trace", [])},
                quiet=quiet, gui_bus=gui_bus,
            )
            write_decision(
                decision="ACCEPT", reason=vote_reason,
                w=w, h=h, vertical=vertical, clip_ok=clip_ok,
                vote_details=vote_details, extra_res=extra_results,
            )

            await encode_queue.put(c)
            validate_queue.task_done()

        except Exception as e:
            stats.final_fail += 1
            log_event(worklog_path, {**ctx, "stage": "VALIDATE", "action": "CRASH", "error": str(e)}, quiet=quiet, gui_bus=gui_bus)
            try:
                remove_with_log(c.get("raw_path", ""), worklog_path=worklog_path, quiet=quiet, ctx=ctx, reason="delete_raw_validate_crash", gui_bus=gui_bus)
            except Exception:
                pass
            validate_queue.task_done()

        finally:
            # Cleanup temporary keyframe directory
            if kf_cleanup_dir and os.path.isdir(kf_cleanup_dir):
                try:
                    shutil.rmtree(kf_cleanup_dir, ignore_errors=True)
                except Exception:
                    pass


async def encode_worker(
    name: str,
    encode_queue: asyncio.Queue,
    *,
    ffmpeg_pool: ProcessPoolExecutor,
    ffmpeg_timeout: int,
    hevc_preset: str,
    hevc_tag: str,
    target_mb: float,
    small_mb_min: float,
    small_mb_max: float,
    keep_original: bool,
    output_dir: str,
    quiz_path: str,
    quiz_lock: asyncio.Lock,
    quiz_hashes: set,
    quiz_hashes_lock: asyncio.Lock,
    questions: List[Dict[str, Any]],
    target_questions: int,
    questions_lock: asyncio.Lock,
    worklog_path: str,
    quiet: bool,
    stats: PipelineStats,
    gui_bus: Optional[GuiEventBus],
):
    loop = asyncio.get_running_loop()
    while True:
        c = await encode_queue.get()
        if c is None:
            encode_queue.task_done()
            break

        ctx = {"worker": name, "id": c["id"], "template": c["template"], "label": c["label"], "keyword": c["keyword"], "raw_path": c["raw_path"], "mp4_path": c["mp4_path"]}

        async with questions_lock:
            if len(questions) >= target_questions:
                if not keep_original:
                    remove_with_log(c["raw_path"], worklog_path=worklog_path, quiet=quiet, ctx=ctx, reason="delete_raw_target_reached_before_encode", gui_bus=gui_bus)
                stats.final_fail += 1
                log_event(worklog_path, {**ctx, "stage": "FINAL", "action": "FAIL", "reason": "target_reached_before_encode"}, quiet=quiet, gui_bus=gui_bus)
                encode_queue.task_done()
                continue

        raw_mb = file_size_mb(c["raw_path"])
        duration = float(c.get("duration") or get_video_duration(c["raw_path"]))
        small_ok = (raw_mb >= float(small_mb_min) and raw_mb <= float(small_mb_max))

        try:
            if small_ok and duration >= 30.0:
                tmp_out = c["mp4_path"] + ".tmp.mp4"
                log_event(worklog_path, {**ctx, "stage": "FFMPEG", "action": "START", "mode": "copy_cut30", "raw_mb": round(raw_mb, 3), "duration": duration}, quiet=quiet, gui_bus=gui_bus)
                _, ok, err = await loop.run_in_executor(None, lambda: ffmpeg_pool.submit(ffmpeg_worker, ("copy_cut30", c["raw_path"], tmp_out, ffmpeg_timeout)).result())
                if not ok:
                    stats.encode_fail += 1
                    log_event(worklog_path, {**ctx, "stage": "FFMPEG", "action": "SKIP", "reason": "copy_cut30_failed", "error": err}, quiet=quiet, gui_bus=gui_bus)
                    remove_with_log(tmp_out, worklog_path=worklog_path, quiet=quiet, ctx=ctx, reason="delete_tmp_copy_cut30_failed", gui_bus=gui_bus)
                    if not keep_original:
                        remove_with_log(c["raw_path"], worklog_path=worklog_path, quiet=quiet, ctx=ctx, reason="delete_raw_copy_cut30_failed", gui_bus=gui_bus)
                    stats.final_fail += 1
                    log_event(worklog_path, {**ctx, "stage": "FINAL", "action": "FAIL", "reason": "ffmpeg_copy_cut30_failed"}, quiet=quiet, gui_bus=gui_bus)
                    encode_queue.task_done()
                    continue

                replace_with_log(tmp_out, c["mp4_path"], worklog_path=worklog_path, quiet=quiet, ctx=ctx, reason="promote_tmp_to_final", gui_bus=gui_bus)
                if not keep_original:
                    remove_with_log(c["raw_path"], worklog_path=worklog_path, quiet=quiet, ctx=ctx, reason="delete_raw_after_copy_cut30", gui_bus=gui_bus)
            else:
                log_event(worklog_path, {**ctx, "stage": "FFMPEG", "action": "START", "mode": "encode_hevc_target_mb_30s", "raw_mb": round(raw_mb, 3), "duration": duration}, quiet=quiet, gui_bus=gui_bus)
                _, ok, err = await loop.run_in_executor(
                    None,
                    lambda: ffmpeg_pool.submit(ffmpeg_worker, ("encode_hevc_target_mb_30s", c["raw_path"], c["mp4_path"], ffmpeg_timeout, target_mb, hevc_preset, hevc_tag)).result(),
                )
                if not ok:
                    stats.encode_fail += 1
                    log_event(worklog_path, {**ctx, "stage": "FFMPEG", "action": "SKIP", "reason": "encode_failed", "error": err}, quiet=quiet, gui_bus=gui_bus)
                    remove_with_log(c["mp4_path"], worklog_path=worklog_path, quiet=quiet, ctx=ctx, reason="delete_output_encode_failed", gui_bus=gui_bus)
                    if not keep_original:
                        remove_with_log(c["raw_path"], worklog_path=worklog_path, quiet=quiet, ctx=ctx, reason="delete_raw_encode_failed", gui_bus=gui_bus)
                    stats.final_fail += 1
                    log_event(worklog_path, {**ctx, "stage": "FINAL", "action": "FAIL", "reason": "ffmpeg_encode_failed"}, quiet=quiet, gui_bus=gui_bus)
                    encode_queue.task_done()
                    continue
                if not keep_original:
                    remove_with_log(c["raw_path"], worklog_path=worklog_path, quiet=quiet, ctx=ctx, reason="delete_raw_after_encode", gui_bus=gui_bus)

            stats.encode_ok += 1

            qtext = (TEMPLATES.get(c["template"]) or {}).get("question") or ""
            label_keys = list(((TEMPLATES.get(c["template"]) or {}).get("labels") or {}).keys())
            opts, answer = pick_4_options(c["label"], label_keys)

            rel_video = os.path.relpath(c["mp4_path"], output_dir).replace("\\", "/")
            quiz_key = f"{qtext}|{'|'.join([o.upper() for o in opts])}"

            async with quiz_hashes_lock:
                if quiz_key in quiz_hashes:
                    remove_with_log(c["mp4_path"], worklog_path=worklog_path, quiet=quiet, ctx=ctx, reason="delete_output_duplicate_question", gui_bus=gui_bus)
                    stats.final_fail += 1
                    log_event(worklog_path, {**ctx, "stage": "FINAL", "action": "FAIL", "reason": "duplicate_question"}, quiet=quiet, gui_bus=gui_bus)
                    encode_queue.task_done()
                    continue
                quiz_hashes.add(quiz_key)

            domanda = {"domanda": qtext, "video": rel_video, "opzioni": [o.upper() for o in opts], "risposta": answer, "durata": 30}

            async with questions_lock:
                if len(questions) >= target_questions:
                    remove_with_log(c["mp4_path"], worklog_path=worklog_path, quiet=quiet, ctx=ctx, reason="delete_output_target_reached_after_encode", gui_bus=gui_bus)
                    stats.final_fail += 1
                    log_event(worklog_path, {**ctx, "stage": "FINAL", "action": "FAIL", "reason": "target_reached_after_encode"}, quiet=quiet, gui_bus=gui_bus)
                    encode_queue.task_done()
                    continue
                questions.append(domanda)
                stats.questions_ok = len(questions)

            async with quiz_lock:
                await loop.run_in_executor(None, lambda: append_quiz_txt(quiz_path, domanda))

            stats.final_ok += 1
            log_event(worklog_path, {**ctx, "stage": "FINAL", "action": "OK", "reason": "question_written", "rel_video": rel_video}, quiet=quiet, gui_bus=gui_bus)
            encode_queue.task_done()

        except Exception as e:
            stats.final_fail += 1
            log_event(worklog_path, {**ctx, "stage": "FINAL", "action": "FAIL", "reason": "encode_worker_exception", "error": str(e)}, quiet=quiet, gui_bus=gui_bus)
            encode_queue.task_done()


# ============================================================
#                 PRODUCER
# ============================================================

async def producer_loop(
    *,
    pexels_api_key: str,
    active_templates: List[str],
    per_label: int,
    min_request_interval: float,
    max_download_attempts_per_question: int,
    video_dir: str,
    download_queue: asyncio.Queue,
    used_output_ids: set,
    used_output_ids_lock: asyncio.Lock,
    processed_ids: set,
    target_questions: int,
    questions: List[Dict[str, Any]],
    questions_lock: asyncio.Lock,
    prefetch_questions: int,
    raw_budget_ok_event: asyncio.Event,
    pause_event: asyncio.Event,
    worklog_path: str,
    quiet: bool,
    gui_bus: Optional[GuiEventBus],
    pexels_max_width: int,
    pexels_min_width: int,
    pexels_min_duration_s: int,
):
    idx = 0
    while True:
        await pause_event.wait()

        async with questions_lock:
            if len(questions) >= target_questions:
                break

        if not raw_budget_ok_event.is_set():
            await asyncio.sleep(0.25)
            continue

        if download_queue.qsize() > prefetch_questions * max_download_attempts_per_question:
            await asyncio.sleep(0.2)
            continue

        idx += 1
        tname = active_templates[(idx - 1) % len(active_templates)]
        labels = (TEMPLATES.get(tname) or {}).get("labels") or {}
        label_keys = list(labels.keys())
        if not label_keys:
            await asyncio.sleep(0.2)
            continue

        correct = random.choice(label_keys)
        keyword = pick_keyword_for_label(labels[correct])
        if not keyword:
            continue

        log_event(worklog_path, {"stage": "PEXELS", "action": "START", "template": tname, "label": correct, "keyword": keyword}, quiet=quiet, gui_bus=gui_bus)

        try:
            videos = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: pexels_search_videos(pexels_api_key, keyword, per_label=per_label, min_interval=min_request_interval),
            )
        except Exception as e:
            log_event(worklog_path, {"stage": "PEXELS", "action": "SKIP", "reason": "pexels_search_error", "error": str(e), "template": tname, "label": correct, "keyword": keyword}, quiet=quiet, gui_bus=gui_bus)
            continue

        random.shuffle(videos)
        async with used_output_ids_lock:
            candidates = prepare_candidates(
                videos, tname, correct, keyword, video_dir,
                max_download_attempts_per_question, used_output_ids, processed_ids,
                pexels_max_width=int(pexels_max_width), pexels_min_width=int(pexels_min_width),
                pexels_min_duration_s=int(pexels_min_duration_s),
                worklog_path=worklog_path, quiet=quiet, gui_bus=gui_bus,
            )

        for c in candidates:
            await download_queue.put(c)


# ============================================================
#                 RUN PIPELINE
# ============================================================

async def run_pipeline(args: argparse.Namespace, *, gui_bus: Optional[GuiEventBus] = None) -> int:
    output_dir = os.path.abspath(args.output_dir)
    video_dir = os.path.abspath(args.video_dir or os.path.join(output_dir, "video"))
    frames_dir = os.path.abspath(args.frames_dir or os.path.join(output_dir, "frames"))
    quiz_path = os.path.join(output_dir, args.output)
    worklog_path = os.path.join(output_dir, args.worklog)
    decisions_csv = os.path.join(output_dir, "decisions.csv")

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(video_dir, exist_ok=True)
    if args.debug_keep_frames:
        os.makedirs(frames_dir, exist_ok=True)

    secrets_path = args.secrets
    if not os.path.isabs(secrets_path):
        secrets_path = os.path.join(output_dir, secrets_path)
    secrets_path = os.path.abspath(secrets_path)

    pexels_api_key = resolve_pexels_key(secrets_path=secrets_path)
    if not pexels_api_key:
        log_event(worklog_path, {"stage": "INIT", "action": "FAIL", "reason": "missing_pexels_api_key", "secrets": secrets_path}, quiet=args.quiet, gui_bus=gui_bus)
        raise SystemExit(f"ERRORE: PEXELS_API_KEY mancante. Mettila in {secrets_path} oppure in ENV.")

    random.seed(args.seed)
    assert_templates_min_labels(10)

    if int(args.max_seconds) != 30:
        raise SystemExit("ERRORE: durata fissa richiesta = 30s. Usa --max-seconds 30.")

    if not ffmpeg_path():
        raise SystemExit("ERRORE: ffmpeg non trovato nel PATH.")
    if not have_encoder("libx265"):
        raise SystemExit("ERRORE: ffmpeg non ha l'encoder libx265.")

    active_templates = [t.strip().lower() for t in args.templates.split(",") if t.strip()]
    active_templates = [t for t in active_templates if t in TEMPLATES]
    if not active_templates:
        raise SystemExit("ERRORE: nessun template valido.")

    used_output_ids = scan_existing_output_ids(video_dir)
    processed_ids = scan_processed_ids_from_worklog(worklog_path)

    stats = PipelineStats()
    device = "cuda" if torch.cuda.is_available() else "cpu"

    log_event(
        worklog_path,
        {
            "stage": "INIT",
            "action": "INFO",
            "device": device,
            "output_dir": output_dir,
            "video_dir": video_dir,
            "quiz_path": quiz_path,
            "worklog_path": worklog_path,
            "decisions_csv": decisions_csv,
            "raw_cap_gb": float(args.raw_cap_gb),
            "raw_resume_ratio": float(args.raw_resume_ratio),
            "clip_threshold": float(args.clip_threshold),
            "clip_min_matches": int(args.clip_min_matches),
            "clip_frames": int(args.clip_frames),
            "enable_blip": bool(args.enable_blip),
            "enable_yolo": bool(args.enable_yolo),
            "enable_grounding": bool(args.enable_grounding),
            "enable_asr": bool(args.enable_asr),
            "enable_ocr": bool(args.enable_ocr),
            "enable_tracking": bool(args.enable_tracking),
            "msg": f"Skip if OUTPUT exists (ids={len(used_output_ids)}) OR ID in worklog (ids={len(processed_ids)}).",
        },
        quiet=args.quiet,
        gui_bus=gui_bus,
    )

    questions: List[Dict[str, Any]] = []
    quiz_hashes = set()

    download_queue: asyncio.Queue = asyncio.Queue(maxsize=50000)
    validate_queue: asyncio.Queue = asyncio.Queue(maxsize=20000)
    encode_queue: asyncio.Queue = asyncio.Queue(maxsize=20000)

    used_output_ids_lock = asyncio.Lock()
    quiz_lock = asyncio.Lock()
    quiz_hashes_lock = asyncio.Lock()
    questions_lock = asyncio.Lock()
    raw_budget_ok_event = asyncio.Event()
    raw_budget_ok_event.set()

    pause_event = asyncio.Event()
    pause_event.set()

    clip_pool = ProcessPoolExecutor(max_workers=max(1, int(args.clip_workers)))
    ffmpeg_pool = ProcessPoolExecutor(max_workers=max(1, int(args.ffmpeg_workers)))
    extra_pool = ThreadPoolExecutor(max_workers=max(1, int(args.extra_workers)))

    hb_task: Optional[asyncio.Task] = None
    budget_task: Optional[asyncio.Task] = None
    producer_task: Optional[asyncio.Task] = None

    try:
        hb_task = asyncio.create_task(
            heartbeat(
                download_queue=download_queue,
                validate_queue=validate_queue,
                encode_queue=encode_queue,
                raw_budget_ok_event=raw_budget_ok_event,
                pause_event=pause_event,
                worklog_path=worklog_path,
                quiet=args.quiet,
                gui_bus=gui_bus,
            )
        )

        budget_task = asyncio.create_task(
            raw_budget_monitor(
                video_dir=video_dir,
                cap_gb=float(args.raw_cap_gb),
                resume_ratio=float(args.raw_resume_ratio),
                poll_s=float(args.raw_budget_poll_s),
                raw_budget_ok_event=raw_budget_ok_event,
                worklog_path=worklog_path,
                quiet=args.quiet,
                gui_bus=gui_bus,
            )
        )

        timeout = aiohttp.ClientTimeout(total=240)
        download_sem = asyncio.Semaphore(max(1, int(args.download_parallel)))

        async with aiohttp.ClientSession(timeout=timeout) as session:
            dn_n = max(1, min(32, int(args.download_parallel)))
            download_tasks = [
                asyncio.create_task(
                    download_worker(
                        f"D{i+1}",
                        session,
                        download_sem,
                        raw_budget_ok_event,
                        pause_event,
                        download_queue,
                        validate_queue,
                        worklog_path=worklog_path,
                        quiet=args.quiet,
                        processed_ids=processed_ids,
                        stats=stats,
                        gui_bus=gui_bus,
                    )
                )
                for i in range(dn_n)
            ]

            v_n = max(1, int(args.validate_workers))
            validate_tasks = [
                asyncio.create_task(
                    validate_worker(
                        f"V{i+1}",
                        validate_queue,
                        encode_queue,
                        clip_pool=clip_pool,
                        extra_pool=extra_pool,
                        device=device,
                        clip_threshold=float(args.clip_threshold),
                        clip_min_matches=int(args.clip_min_matches),
                        clip_frames=int(args.clip_frames),
                        frames_dir=frames_dir,
                        keep_frames=bool(args.debug_keep_frames),
                        enable_blip=bool(args.enable_blip),
                        enable_yolo=bool(args.enable_yolo),
                        enable_grounding=bool(args.enable_grounding),
                        enable_asr=bool(args.enable_asr),
                        enable_ocr=bool(args.enable_ocr),
                        enable_tracking=bool(args.enable_tracking),
                        yolo_conf=float(args.yolo_conf),
                        owlv2_thresh=float(args.owlv2_thresh),
                        worklog_path=worklog_path,
                        quiet=args.quiet,
                        stats=stats,
                        gui_bus=gui_bus,
                        decisions_csv=decisions_csv,
                    )
                )
                for i in range(v_n)
            ]

            e_n = max(1, int(args.ffmpeg_workers))
            encode_tasks = [
                asyncio.create_task(
                    encode_worker(
                        f"E{i+1}",
                        encode_queue,
                        ffmpeg_pool=ffmpeg_pool,
                        ffmpeg_timeout=int(args.ffmpeg_timeout),
                        hevc_preset=str(args.hevc_preset),
                        hevc_tag=str(args.hevc_tag),
                        target_mb=float(args.target_mb),
                        small_mb_min=float(args.small_mb_min),
                        small_mb_max=float(args.small_mb_max),
                        keep_original=bool(args.keep_original),
                        output_dir=output_dir,
                        quiz_path=quiz_path,
                        quiz_lock=quiz_lock,
                        quiz_hashes=quiz_hashes,
                        quiz_hashes_lock=quiz_hashes_lock,
                        questions=questions,
                        target_questions=int(args.target_questions),
                        questions_lock=questions_lock,
                        worklog_path=worklog_path,
                        quiet=args.quiet,
                        stats=stats,
                        gui_bus=gui_bus,
                    )
                )
                for i in range(e_n)
            ]

            producer_task = asyncio.create_task(
                producer_loop(
                    pexels_api_key=pexels_api_key,
                    active_templates=active_templates,
                    per_label=int(args.per_label),
                    min_request_interval=float(args.min_request_interval),
                    max_download_attempts_per_question=int(args.max_download_attempts_per_question),
                    video_dir=video_dir,
                    download_queue=download_queue,
                    used_output_ids=used_output_ids,
                    used_output_ids_lock=used_output_ids_lock,
                    processed_ids=processed_ids,
                    target_questions=int(args.target_questions),
                    questions=questions,
                    questions_lock=questions_lock,
                    prefetch_questions=int(args.prefetch_questions),
                    raw_budget_ok_event=raw_budget_ok_event,
                    pause_event=pause_event,
                    worklog_path=worklog_path,
                    quiet=args.quiet,
                    gui_bus=gui_bus,
                    pexels_max_width=int(args.pexels_max_width),
                    pexels_min_width=int(args.pexels_min_width),
                    pexels_min_duration_s=int(args.pexels_min_duration),
                )
            )

            while True:
                await asyncio.sleep(0.9)
                if gui_bus is not None:
                    gui_bus.emit({
                        "stage": "STATS",
                        "action": "INFO",
                        "stats": stats.__dict__,
                        "download_q": int(download_queue.qsize()),
                        "validate_q": int(validate_queue.qsize()),
                        "encode_q": int(encode_queue.qsize()),
                    })
                async with questions_lock:
                    if len(questions) >= int(args.target_questions):
                        break

            producer_task.cancel()
            try:
                await producer_task
            except BaseException:
                pass

            for _ in download_tasks:
                await download_queue.put(None)
            await download_queue.join()

            for _ in validate_tasks:
                await validate_queue.put(None)
            await validate_queue.join()

            for _ in encode_tasks:
                await encode_queue.put(None)
            await encode_queue.join()

            stats.questions_ok = len(questions)
            log_event(worklog_path, {"stage": "DONE", "action": "OK", "questions_ok": len(questions), "quiz_path": quiz_path, "video_dir": video_dir, "decisions_csv": decisions_csv}, quiet=args.quiet, gui_bus=gui_bus)
            return 0

    finally:
        if hb_task is not None:
            hb_task.cancel()
            try:
                await hb_task
            except BaseException:
                pass
        if budget_task is not None:
            budget_task.cancel()
            try:
                await budget_task
            except BaseException:
                pass
        try:
            clip_pool.shutdown(wait=True)
        except Exception:
            pass
        try:
            ffmpeg_pool.shutdown(wait=True)
        except Exception:
            pass
        try:
            extra_pool.shutdown(wait=True)
        except Exception:
            pass


# ============================================================
#                 GUI APP (semplice)
# ============================================================

class GeneratorGUI:
    def __init__(self):
        if not HAVE_TK:
            raise RuntimeError("tkinter non disponibile.")
        self.root = tk.Tk()
        self.root.title("Quiz Video Generator (ORIENTATION -> CLIP ONLY)")
        self.root.geometry("1200x980")

        self.gui_bus = GuiEventBus()
        self.pipeline_thread: Optional[threading.Thread] = None
        self.running = False
        self.stats = PipelineStats()

        self._build_ui()
        self.root.after(120, self._poll_events)

    def _build_ui(self):
        root = ttk.Frame(self.root)
        root.pack(fill="both", expand=True, padx=10, pady=10)

        cfg = ttk.LabelFrame(root, text="Config")
        cfg.pack(fill="x")

        self.output_dir = tk.StringVar(value=os.path.abspath(r"c:\quiz video") if IS_WINDOWS else os.path.abspath("."))
        self.secrets_path = tk.StringVar(value=os.path.join(self.output_dir.get(), "secrets.json"))
        self.target_q = tk.IntVar(value=10000)

        self.raw_cap_gb = tk.DoubleVar(value=10.0)
        self.raw_resume_ratio = tk.DoubleVar(value=0.5)

        row1 = ttk.Frame(cfg); row1.pack(fill="x", padx=8, pady=4)
        ttk.Label(row1, text="Output dir:").pack(side="left")
        ttk.Entry(row1, textvariable=self.output_dir, width=80).pack(side="left", padx=8)
        ttk.Button(row1, text="Browse", command=self._browse_output).pack(side="left")

        row2 = ttk.Frame(cfg); row2.pack(fill="x", padx=8, pady=4)
        ttk.Label(row2, text="Secrets json:").pack(side="left")
        ttk.Entry(row2, textvariable=self.secrets_path, width=80).pack(side="left", padx=8)
        ttk.Button(row2, text="Reload", command=self._reload_secrets).pack(side="left")

        row3 = ttk.Frame(cfg); row3.pack(fill="x", padx=8, pady=4)
        ttk.Label(row3, text="Target questions:").pack(side="left")
        ttk.Entry(row3, textvariable=self.target_q, width=10).pack(side="left", padx=8)

        row4 = ttk.Frame(cfg); row4.pack(fill="x", padx=8, pady=4)
        ttk.Label(row4, text="RAW cap (GB):").pack(side="left")
        ttk.Entry(row4, textvariable=self.raw_cap_gb, width=10).pack(side="left", padx=8)
        ttk.Label(row4, text="Resume ratio:").pack(side="left")
        ttk.Entry(row4, textvariable=self.raw_resume_ratio, width=10).pack(side="left", padx=8)

        keys = ttk.LabelFrame(root, text="Pexels API Key (salva in secrets.json)")
        keys.pack(fill="x", pady=(8, 0))

        self.pexels_key = tk.StringVar(value="")

        kr1 = ttk.Frame(keys); kr1.pack(fill="x", padx=8, pady=4)
        ttk.Label(kr1, text="PEXELS_API_KEY:").pack(side="left")
        ttk.Entry(kr1, textvariable=self.pexels_key, show="*", width=95).pack(side="left", padx=8)

        kr3 = ttk.Frame(keys); kr3.pack(fill="x", padx=8, pady=6)
        ttk.Button(kr3, text="Save key", command=self._save_key).pack(side="left")

        ctrl = ttk.LabelFrame(root, text="Controls")
        ctrl.pack(fill="x", pady=(8, 0))

        self.btn_start = ttk.Button(ctrl, text="Start", command=self.start)
        self.btn_stop = ttk.Button(ctrl, text="Stop (pause)", command=self.stop, state="disabled")
        self.btn_start.pack(side="left", padx=6, pady=6)
        self.btn_stop.pack(side="left", padx=6, pady=6)

        self.status = tk.StringVar(value="Idle")
        ttk.Label(ctrl, textvariable=self.status).pack(side="left", padx=18)

        st = ttk.LabelFrame(root, text="Stats")
        st.pack(fill="x", pady=(8, 0))
        self.lbl_stats = tk.StringVar(value="(no stats yet)")
        ttk.Label(st, textvariable=self.lbl_stats).pack(anchor="w", padx=8, pady=6)

        qf = ttk.LabelFrame(root, text="Queues")
        qf.pack(fill="x", pady=(8, 0))
        self.lbl_queues = tk.StringVar(value="download_q=0 | validate_q=0 | encode_q=0")
        ttk.Label(qf, textvariable=self.lbl_queues).pack(anchor="w", padx=8, pady=6)

        logf = ttk.LabelFrame(root, text="Live log (events)")
        logf.pack(fill="both", expand=True, pady=(8, 0))
        self.log_text = tk.Text(logf, wrap="word")
        self.log_text.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        scroll = ttk.Scrollbar(logf, orient="vertical", command=self.log_text.yview)
        scroll.pack(side="right", fill="y", padx=8, pady=8)
        self.log_text.configure(yscrollcommand=scroll.set)

        self._reload_secrets()
        self._update_labels()

    def _browse_output(self):
        if filedialog is None:
            return
        d = filedialog.askdirectory()
        if d:
            self.output_dir.set(d)
            self.secrets_path.set(os.path.join(d, "secrets.json"))
            self._reload_secrets()

    def _reload_secrets(self):
        sp = self.secrets_path.get().strip()
        s = load_secrets(sp)
        self.pexels_key.set(s.get("PEXELS_API_KEY", os.environ.get("PEXELS_API_KEY", "")))

    def _save_key(self):
        sp = self.secrets_path.get().strip()
        if not sp:
            messagebox.showerror("Error", "secrets path vuoto")
            return
        save_secrets(sp, self.pexels_key.get())
        messagebox.showinfo("OK", f"Salvato: {sp}")

    def _append_log(self, line: str):
        self.log_text.insert("end", line + "\n")
        self.log_text.see("end")

    def _update_labels(self):
        s = self.stats
        self.lbl_stats.set(
            f"questions_ok={s.questions_ok} | final_ok={s.final_ok} | final_fail={s.final_fail} | "
            f"dl_ok={s.downloads_ok}/dl_fail={s.downloads_fail} | "
            f"clip_ok={s.clip_ok}/clip_fail={s.clip_fail} | "
            f"encode_ok={s.encode_ok}/encode_fail={s.encode_fail}"
        )

    def _poll_events(self):
        try:
            while True:
                ev = self.gui_bus.q.get_nowait()
                stage = ev.get("stage", "?")
                action = ev.get("action", "?")
                reason = ev.get("reason", "")
                msg = ev.get("msg", "")
                pid = ev.get("id", "")
                tail = ev.get("mp4_path") or ev.get("raw_path") or ev.get("path") or ""
                tail = os.path.basename(tail) if tail else ""
                line = f"{ev.get('ts','')} [{stage}] {action} {reason} id={pid} {tail} {msg}".strip()
                self._append_log(line)

                if stage == "STATS" and isinstance(ev.get("stats"), dict):
                    d = ev["stats"]
                    for k, v in d.items():
                        if hasattr(self.stats, k):
                            setattr(self.stats, k, int(v))
                    self.lbl_queues.set(f"download_q={ev.get('download_q')} | validate_q={ev.get('validate_q')} | encode_q={ev.get('encode_q')}")
                    self._update_labels()
        except queue_mod.Empty:
            pass
        self.root.after(150, self._poll_events)

    def start(self):
        if self.running:
            return

        out = self.output_dir.get().strip()
        sp = self.secrets_path.get().strip()
        if not out:
            messagebox.showerror("Error", "Output dir vuoto")
            return
        if not sp:
            messagebox.showerror("Error", "Secrets path vuoto")
            return

        save_secrets(sp, self.pexels_key.get())
        pex = resolve_pexels_key(secrets_path=sp)
        if not pex:
            messagebox.showerror("Missing key", "Manca PEXELS_API_KEY (salvala in secrets.json).")
            return

        self.status.set("Running...")
        self.running = True
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")

        args = build_arg_parser().parse_args([])
        args.output_dir = out
        args.secrets = sp
        args.target_questions = int(self.target_q.get())

        args.per_label = 120
        args.max_download_attempts_per_question = 30
        args.prefetch_questions = 60
        args.download_parallel = 12
        args.clip_workers = 6
        args.validate_workers = 1
        args.ffmpeg_workers = 6

        args.raw_cap_gb = float(self.raw_cap_gb.get())
        args.raw_resume_ratio = float(self.raw_resume_ratio.get())

        def _thread_main():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(run_pipeline(args, gui_bus=self.gui_bus))
            except BaseException as e:
                self.gui_bus.emit({"stage": "GUI", "action": "CRASH", "msg": str(e)})
            finally:
                try:
                    loop.stop()
                    loop.close()
                except Exception:
                    pass

        self.pipeline_thread = threading.Thread(target=_thread_main, daemon=True)
        self.pipeline_thread.start()

    def stop(self):
        self.status.set("Stop not implemented (close window).")


# ============================================================
#                 ARGS
# ============================================================

def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Quiz Video Generator (PEXELS) — majority vote multi-module pipeline."
    )

    ap.add_argument("--gui", action="store_true", help="Avvia GUI")
    ap.add_argument("--output-dir", default=".")
    ap.add_argument("--video-dir", default=None)
    ap.add_argument("--frames-dir", default=None)
    ap.add_argument("--debug-keep-frames", action="store_true")

    ap.add_argument("--output", default="domande_quiz_video.txt")
    ap.add_argument("--worklog", default="work_log.jsonl")
    ap.add_argument("--secrets", default="secrets.json")

    ap.add_argument("--target-questions", type=int, default=5)
    ap.add_argument("--templates", default="sports,sports_2,sports_3,animals,animals_wild,animals_more,animals_sea,colors,colors_2,lighting,emotions,people_actions,family,vehicles,vehicles_2,traffic,weather,weather_2,seasons,food,food_2,drinks,nature,nature_2,plants,tech,tech_2,gaming,places,places_2,travel,music,dance,concert,jobs,jobs_2,jobs_3,objects")

    ap.add_argument("--per-label", type=int, default=120)
    ap.add_argument("--max-seconds", type=int, default=30)
    ap.add_argument("--max-download-attempts-per-question", type=int, default=25)
    ap.add_argument("--min-request-interval", type=float, default=1.8)
    ap.add_argument("--seed", type=int, default=123)
    ap.add_argument("--quiet", action="store_true")

    ap.add_argument("--ffmpeg-workers", type=int, default=6)
    ap.add_argument("--clip-workers", type=int, default=6)
    ap.add_argument("--validate-workers", type=int, default=1)
    ap.add_argument("--download-parallel", type=int, default=12)
    ap.add_argument("--prefetch-questions", type=int, default=60)

    ap.add_argument("--hevc-preset", default=DEFAULT_HEVC_PRESET)
    ap.add_argument("--hevc-tag", default=DEFAULT_HEVC_TAG)
    ap.add_argument("--ffmpeg-timeout", type=int, default=900)
    ap.add_argument("--keep-original", action="store_true")

    ap.add_argument("--clip-threshold", type=float, default=DEFAULT_CLIP_THRESHOLD)
    ap.add_argument("--clip-min-matches", type=int, default=DEFAULT_CLIP_MIN_MATCHES)
    ap.add_argument("--clip-frames", type=int, default=DEFAULT_CLIP_FRAMES)

    ap.add_argument("--raw-cap-gb", type=float, default=DEFAULT_RAW_CAP_GB)
    ap.add_argument("--raw-resume-ratio", type=float, default=DEFAULT_RAW_RESUME_RATIO)
    ap.add_argument("--raw-budget-poll-s", type=float, default=DEFAULT_RAW_BUDGET_POLL_S)

    ap.add_argument("--small-mb-min", type=float, default=DEFAULT_SMALL_MB_MIN)
    ap.add_argument("--small-mb-max", type=float, default=DEFAULT_SMALL_MB_MAX)
    ap.add_argument("--target-mb", type=float, default=DEFAULT_TARGET_MB)

    ap.add_argument("--pexels-max-width", type=int, default=DEFAULT_PEXELS_MAX_WIDTH)
    ap.add_argument("--pexels-min-width", type=int, default=DEFAULT_PEXELS_MIN_WIDTH)
    ap.add_argument("--pexels-min-duration", type=int, default=DEFAULT_PEXELS_MIN_DURATION)

    # ---- Extra module flags ----
    ap.add_argument(
        "--no-blip", dest="enable_blip", action="store_false", default=DEFAULT_ENABLE_BLIP,
        help="Disabilita BLIP VQA (Salesforce/blip-vqa-base)",
    )
    ap.add_argument(
        "--no-yolo", dest="enable_yolo", action="store_false", default=DEFAULT_ENABLE_YOLO,
        help="Disabilita YOLO (yolov8n)",
    )
    ap.add_argument(
        "--no-grounding", dest="enable_grounding", action="store_false",
        default=DEFAULT_ENABLE_GROUNDING,
        help="Disabilita OWLv2 open-vocabulary grounding",
    )
    ap.add_argument(
        "--enable-asr", dest="enable_asr", action="store_true", default=DEFAULT_ENABLE_ASR,
        help="Abilita ASR con faster-whisper (lento su CPU, disabilitato di default)",
    )
    ap.add_argument(
        "--enable-ocr", dest="enable_ocr", action="store_true", default=DEFAULT_ENABLE_OCR,
        help="Abilita OCR con pytesseract (richiede tesseract-ocr, disabilitato di default)",
    )
    ap.add_argument(
        "--no-tracking", dest="enable_tracking", action="store_false",
        default=DEFAULT_ENABLE_TRACKING,
        help="Disabilita IOU tracking across keyframes",
    )
    ap.add_argument(
        "--yolo-conf", type=float, default=DEFAULT_YOLO_CONF,
        help="Soglia di confidenza YOLO (default 0.30)",
    )
    ap.add_argument(
        "--owlv2-thresh", type=float, default=DEFAULT_OWLV2_THRESH,
        help="Soglia di score OWLv2 (default 0.10)",
    )
    ap.add_argument(
        "--extra-workers", type=int, default=DEFAULT_EXTRA_WORKERS,
        help="Thread pool size per extra checks (BLIP/YOLO/OWLv2/...) (default 4)",
    )

    return ap


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = build_arg_parser()
    args = ap.parse_args(list(argv) if argv is not None else None)

    if args.gui:
        if not HAVE_TK:
            print("ERRORE: tkinter non disponibile.")
            return 2
        GeneratorGUI().root.mainloop()
        return 0

    return asyncio.run(run_pipeline(args))


if __name__ == "__main__":
    raise SystemExit(main())
