"""
Sentiment Engine — core analysis module.
Polarity via VADER, emotion detection via lexicon.
"""
import re
import json
import urllib.parse
import urllib.request
import html as html_mod
from collections import Counter
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# ── Emotion Lexicon ──
EMOTION_LEXICON = {
    "joy": {"joy", "happy", "delighted", "thrilled", "excited", "ecstatic", "elated",
            "cheerful", "glad", "pleased", "proud", "accomplished", "amazing",
            "wonderful", "fantastic", "brilliant", "excellent", "love", "loved",
            "beautiful", "gorgeous", "magnificent", "success", "successful",
            "win", "winner", "triumph", "breakthrough", "innovation", "incredible",
            "genius", "visionary", "legend", "legendary", "iconic", "masterpiece",
            "inspiring", "inspired", "brilliance", "greatness", "fav", "favorite"},
    "anger": {"anger", "angry", "furious", "outraged", "enraged", "frustrated",
              "frustration", "infuriated", "irate", "livid", "mad", "hostile",
              "aggressive", "rage", "wrath", "irritated", "annoyed", "annoying",
              "resentment", "bitter", "outrage", "fuming", "hate", "hatred",
              "despise", "contempt", "divisive", "polarizing", "toxic", "poisonous"},
    "sadness": {"sad", "sadness", "unhappy", "depressed", "depressing", "miserable",
                "heartbroken", "devastated", "grief", "grieving", "mourn", "mourning",
                "sorrow", "sorrowful", "melancholy", "gloomy", "hopeless", "despair",
                "desperate", "crying", "tears", "lonely", "rejected", "hurt",
                "painful", "suffering", "tragedy", "tragic", "disappointed",
                "disappointment", "regret", "regretful", "heartbreak", "pain", "loss"},
    "fear": {"fear", "afraid", "scared", "frightened", "terrified", "horrified",
             "anxious", "anxiety", "worried", "worry", "nervous", "panicked",
             "panic", "terrifying", "dread", "dreadful", "alarmed", "uneasy",
             "distressed", "threatened", "ominous", "menacing", "dangerous",
             "unsafe", "vulnerable", "insecure", "hesitant", "uncertain",
             "suspicious", "skeptical", "doubt", "doubtful", "concerned",
             "alarming", "worrying", "frightening", "unsettling", "disturbing"},
    "surprise": {"surprise", "surprised", "shocked", "shocking", "astonished",
                 "astonishing", "amazed", "amazing", "stunned", "stunning",
                 "startled", "unexpected", "unbelievable", "incredible",
                 "remarkable", "extraordinary", "staggering", "baffling",
                 "baffled", "perplexed", "bewildered", "dumbfounded", "floored",
                 "speechless", "mind-blowing", "jaw-dropping", "eye-opening",
                 "bombshell", "revelation", "unprecedented", "historic"},
    "trust": {"trust", "trusted", "trustworthy", "reliable", "dependable",
              "honest", "honesty", "integrity", "sincere", "genuine", "authentic",
              "faithful", "loyal", "committed", "responsible", "accountable",
              "credible", "reputable", "respected", "respectable", "admirable",
              "admire", "admired", "confident", "reassuring", "assured",
              "safe", "secure", "stable", "solid", "consistent", "transparent"},
    "anticipation": {"anticipation", "anticipate", "expect", "expecting",
                     "expectation", "eager", "eagerly", "looking forward",
                     "hopeful", "hope", "optimistic", "promising", "potential",
                     "upcoming", "forthcoming", "impending", "imminent",
                     "planned", "preparing", "prepare", "ready", "excited",
                     "buzz", "hype", "hyped", "curious", "curiosity", "interest",
                     "interested", "fascinated", "fascinating", "intriguing",
                     "speculation", "speculative", "buzzing", "buildup"},
    "disgust": {"disgust", "disgusted", "disgusting", "revolting", "repulsive",
                "repugnant", "nauseating", "sickening", "appalling", "appall",
                "horrible", "horrific", "hideous", "atrocious", "abhorrent",
                "despicable", "contemptible", "loathsome", "detestable",
                "distasteful", "offensive", "vile", "gross", "nasty", "foul",
                "deplorable", "shameful"},
}

INTENSIFIERS = {"very": 1.3, "extremely": 1.5, "incredibly": 1.5, "absolutely": 1.4,
                "totally": 1.3, "completely": 1.3, "utterly": 1.5, "deeply": 1.3,
                "highly": 1.2, "intensely": 1.4, "really": 1.1, "so": 1.1,
                "remarkably": 1.4, "exceptionally": 1.5}

_analyzer = None

def get_analyzer():
    global _analyzer
    if _analyzer is None:
        import nltk
        try:
            nltk.data.find('sentiment/vader_lexicon')
        except LookupError:
            nltk.download('vader_lexicon', quiet=True)
        _analyzer = SentimentIntensityAnalyzer()
    return _analyzer


def fetch_google_news(name, max_results=50):
    """Fetch latest news mentions from Google News RSS."""
    query = urllib.parse.quote(f'{name}')
    url = f'https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en'
    
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
    })
    
    try:
        html = urllib.request.urlopen(req, timeout=10).read().decode('utf-8', errors='replace')
    except Exception as e:
        return [], str(e)
    
    items = re.findall(r'<item>(.*?)</item>', html, re.DOTALL)
    mentions = []
    
    for item in items:
        title_m = re.search(r'<title>(.*?)</title>', item)
        desc_m = re.search(r'<description>(.*?)</description>', item)
        source_m = re.search(r'<source[^>]*>(.*?)</source>', item)
        link_m = re.search(r'<link>(.*?)</link>', item)
        
        title = html_mod.unescape(title_m.group(1).strip()) if title_m else ''
        desc_raw = html_mod.unescape(desc_m.group(1)) if desc_m else ''
        desc = re.sub(r'<[^>]+>', '', desc_raw).strip()
        source = html_mod.unescape(source_m.group(1).strip()) if source_m else 'News'
        link = html_mod.unescape(link_m.group(1).strip()) if link_m else ''
        
        text = title
        if desc and desc != title and not title.endswith(desc):
            text += '. ' + desc
        
        if len(text) > 40:
            mentions.append({"text": text[:800], "source": source, "url": link})
        
        if len(mentions) >= max_results:
            break
    
    return mentions, None


def detect_emotions(text):
    """Detect emotions in text using lexicon-based approach."""
    text_lower = text.lower()
    words = re.findall(r'\b[a-zA-Z][a-zA-Z\']{2,}\b', text_lower)
    bigrams = set(' '.join(words[i:i+2]) for i in range(len(words)-1))
    
    emotion_scores = {}
    for emotion, keywords in EMOTION_LEXICON.items():
        score = 0
        for word in words:
            if word in keywords:
                score += 1.5
        for bigram in bigrams:
            if bigram in keywords:
                score += 3
        
        for i, w in enumerate(words):
            if w in INTENSIFIERS:
                for j in range(i+1, min(i+4, len(words))):
                    for emo2, kw2 in EMOTION_LEXICON.items():
                        if words[j] in kw2:
                            score += INTENSIFIERS[w] - 1
                            break
        
        if score > 0:
            emotion_scores[emotion] = score
    
    if emotion_scores:
        max_score = max(emotion_scores.values())
        if max_score > 0:
            emotion_scores = {k: round(v / max_score * 100) for k, v in emotion_scores.items()}
    
    return emotion_scores


def analyze(person_name, mentions=None):
    """Run full sentiment analysis on a person."""
    analyzer = get_analyzer()
    
    if mentions is None:
        mentions, error = fetch_google_news(person_name)
        if error:
            return {"error": error, "person": person_name}
    
    if not mentions:
        return {
            "person": person_name,
            "error": "No mentions found",
            "results": [],
            "summary": {}
        }
    
    results = []
    for mention in mentions:
        scores = analyzer.polarity_scores(mention["text"])
        emotions = detect_emotions(mention["text"])
        
        results.append({
            "source": mention.get("source", "unknown"),
            "text": mention["text"][:300],
            "compound": round(scores["compound"], 4),
            "pos": round(scores["pos"], 4),
            "neg": round(scores["neg"], 4),
            "neu": round(scores["neu"], 4),
            "emotions": emotions,
            "url": mention.get("url", ""),
        })
    
    # Aggregate summary
    compounds = [r["compound"] for r in results]
    avg_compound = round(sum(compounds) / len(compounds), 4) if compounds else 0
    
    total = len(results)
    positive = sum(1 for c in compounds if c >= 0.05)
    negative = sum(1 for c in compounds if c <= -0.05)
    neutral = total - positive - negative
    
    emotion_sums = Counter()
    emotion_counts = Counter()
    for r in results:
        for emo, score in r["emotions"].items():
            emotion_sums[emo] += score
            emotion_counts[emo] += 1
    top_emotions = {}
    for emo in emotion_sums:
        top_emotions[emo] = round(emotion_sums[emo] / emotion_counts[emo])
    top_emotions = dict(sorted(top_emotions.items(), key=lambda x: -x[1]))
    
    if avg_compound >= 0.35:
        sentiment_label = "Very Positive"
    elif avg_compound >= 0.05:
        sentiment_label = "Positive"
    elif avg_compound > -0.05:
        sentiment_label = "Neutral"
    elif avg_compound > -0.35:
        sentiment_label = "Negative"
    else:
        sentiment_label = "Very Negative"
    
    # Source diversity
    sources = Counter(r["source"] for r in results)
    
    summary = {
        "avg_compound": avg_compound,
        "sentiment_label": sentiment_label,
        "total": total,
        "positive": positive,
        "neutral": neutral,
        "negative": negative,
        "pct_positive": round(positive/total*100) if total else 0,
        "pct_neutral": round(neutral/total*100) if total else 0,
        "pct_negative": round(negative/total*100) if total else 0,
        "top_emotions": top_emotions,
        "sources": dict(sources.most_common(10)),
    }
    
    return {
        "person": person_name,
        "summary": summary,
        "results": results,
    }