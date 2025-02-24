import gradio as gr
from gnews import GNews
from groq import Groq
from deep_translator import GoogleTranslator
import os
import datetime
import concurrent.futures
import time
import random
import cachetools
import logging
from dotenv import load_dotenv

# Initialize Groq client
GROQ_API_KEY = "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"  # Replace with your API key
groq_client = Groq(api_key=GROQ_API_KEY)

# Initialize Google News
gn = GNews(language="en", country="IN", period="1d")

# Supported languages
LANGUAGES = {"English": "en", "Hindi": "hi", "Bengali": "bn", "Tamil": "ta", "Telugu": "te", "Marathi": "mr", "Gujarati": "gu"}

# Cache for API responses
cache = cachetools.TTLCache(maxsize=100, ttl=300)

# Default genre images
GENRE_IMAGES = {genre: f"https://via.placeholder.com/300?text={genre.replace(' ', '+')}" for genre in ["Top Stories", "Business", "Technology", "Entertainment", "Sports", "Science", "Health", "World"]}

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def retry_with_exponential_backoff(func, max_retries=5, initial_delay=1, backoff_factor=2):
    """Handles API rate limits with exponential backoff."""
    def wrapper(*args, **kwargs):
        retries = 0
        delay = initial_delay
        while retries < max_retries:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if "rate limit" in str(e).lower():
                    retries += 1
                    logger.warning(f"Rate limit hit. Retrying in {delay} seconds... (Attempt {retries}/{max_retries})")
                    time.sleep(delay)
                    delay *= backoff_factor
                else:
                    raise e
        raise Exception("Max retries reached. Please try again later.")
    return wrapper

@cachetools.cached(cache)
@retry_with_exponential_backoff
def summarize_with_groq(text):
    """Summarizes news using Groq API."""
    try:
        prompt = f"Summarize the following text in approximately 250 words:\n\n{text}"
        response = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="mixtral-8x7b-32768",
            max_tokens=800,
            temperature=0.5
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Error: {e}"

def translate_text(text, target_language):
    """Translates text to the target language."""
    if target_language != "English":
        return GoogleTranslator(source='en', target=LANGUAGES[target_language]).translate(text)
    return text

@cachetools.cached(cache)
def fetch_news(query, genre, language):
    """Fetches news from Google News and summarizes it."""
    try:
        news_articles = gn.get_news(query)
        articles = []
        if news_articles:
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [(article, executor.submit(summarize_with_groq, article.get('description', ''))) for article in news_articles[:5]]
                for article, summary_future in futures:
                    summary = summary_future.result()
                    headline = article.get('title', 'No Title')
                    published_date = article.get('published date', 'Unknown Date')

                    if language != "English":
                        summary = translate_text(summary, language)
                        headline = translate_text(headline, language)

                    articles.append({
                        "headline": headline,
                        "date": published_date,
                        "summary": summary,
                        "reference": article.get('url', '#'),
                        "thumbnail": GENRE_IMAGES.get(genre, "https://via.placeholder.com/300"),
                        "views": random.randint(100, 10000)
                    })
        else:
            articles.append({"headline": translate_text("No news found", language), "date": "", "summary": "", "reference": "", "thumbnail": "", "views": 0})
        return articles
    except Exception as e:
        return [{"headline": translate_text(f"Error fetching news: {e}", language), "date": "", "summary": "", "reference": "", "thumbnail": "", "views": 0}]

def display_news(search_mode, keyword, location, genre, language):
    """Displays formatted news articles with sharing options."""
    query = keyword if search_mode == "Keyword Only" else f"{location} {genre}"
    articles = fetch_news(query, genre, language)

    return "".join([f"""
    <div style='border:1px solid #ddd;padding:10px;margin-bottom:10px;border-radius:5px;'>
        <img src='{article['thumbnail']}' alt='By Kalyug Patrika' style='max-width:300px;height:auto;margin-bottom:10px;'>
        <h3>{article['headline']}</h3>
        <p><strong>📅 Date:</strong> {article['date']}</p>
        <p><strong>📝 Summary:</strong> {article['summary']}</p>
        <p><strong>🌐 Reference:</strong> <a href='{article['reference']}' target='_blank'>Read more</a></p>
        <p><strong>👀 Live Views:</strong> {article['views']}</p>
        
        <p><strong>🔗 Share:</strong>
            <a href='https://twitter.com/intent/tweet?url={article['reference']}' target='_blank' style='margin-right:10px;'>
                <i class='fab fa-twitter'></i>
            </a>
            <a href='https://www.facebook.com/sharer/sharer.php?u={article['reference']}' target='_blank' style='margin-right:10px;'>
                <i class='fab fa-facebook'></i>
            </a>
            <a href='https://www.linkedin.com/sharing/share-offsite/?url={article['reference']}' target='_blank' style='margin-right:10px;'>
                <i class='fab fa-linkedin'></i>
            </a>
            <a href='https://wa.me/?text={article['reference']}' target='_blank' style='margin-right:10px;'>
                <i class='fab fa-whatsapp'></i>
            </a>
            <a href='https://pinterest.com/pin/create/button/?url={article['reference']}' target='_blank'>
                <i class='fab fa-pinterest'></i>
            </a>
        </p>
    </div>
    """ for article in articles])

def update_inputs(search_mode):
    """Handles UI visibility for search modes."""
    if search_mode == "Keyword Only":
        return gr.update(visible=True), gr.update(visible=False), gr.update(visible=False)
    return gr.update(visible=False), gr.update(visible=True), gr.update(visible=True)

# Gradio UI
demo = gr.Blocks()
with demo:
    gr.Markdown("# 📰 कलयुग पत्रिका")
    gr.HTML("<link rel='stylesheet' href='https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css'>")

    search_mode = gr.Radio(label="Search Mode", choices=["Keyword Only", "Location + Genre"], value="Keyword Only")
    keyword_input = gr.Textbox(label="Keyword", placeholder="Enter a keyword")
    location_input = gr.Textbox(label="Location", placeholder="Enter location", visible=False)
    genre_dropdown = gr.Dropdown(label="Genre", choices=list(GENRE_IMAGES.keys()), visible=False)
    language_dropdown = gr.Dropdown(label="Language", choices=list(LANGUAGES.keys()), value="English")
    
    fetch_button = gr.Button("Fetch News")
    output_html = gr.HTML()

    search_mode.change(update_inputs, inputs=[search_mode], outputs=[keyword_input, location_input, genre_dropdown])
    fetch_button.click(display_news, inputs=[search_mode, keyword_input, location_input, genre_dropdown, language_dropdown], outputs=output_html)

demo.launch()