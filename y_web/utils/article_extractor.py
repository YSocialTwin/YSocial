import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urlparse


def extract_article_info(url):
    """
    Extract title and description from a web page URL
    Returns a dictionary with title, summary, and source
    """
    try:
        # Set headers to mimic a real browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # Fetch the page with timeout
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Parse the HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract title
        title = extract_title(soup, url)
        
        # Extract description/summary
        summary = extract_description(soup)
        
        # Extract source domain
        source = extract_source(url)
        
        return {
            'title': title,
            'summary': summary,
            'source': source,
            'url': url
        }
        
    except Exception as e:
        print(f"Error extracting article info from {url}: {e}")
        # Fallback to basic info
        return {
            'title': f"Shared Link: {urlparse(url).netloc}",
            'summary': "User shared article",
            'source': urlparse(url).netloc,
            'url': url
        }


def extract_title(soup, url):
    """Extract page title from various sources"""
    # Try Open Graph title first
    og_title = soup.find('meta', property='og:title')
    if og_title and og_title.get('content'):
        return og_title['content'].strip()
    
    # Try Twitter title
    twitter_title = soup.find('meta', attrs={'name': 'twitter:title'})
    if twitter_title and twitter_title.get('content'):
        return twitter_title['content'].strip()
    
    # Try regular title tag
    title_tag = soup.find('title')
    if title_tag and title_tag.text:
        return title_tag.text.strip()
    
    # Fallback to domain name
    return f"Article from {urlparse(url).netloc}"


def extract_description(soup):
    """Extract page description from various sources"""
    # Try Open Graph description
    og_desc = soup.find('meta', property='og:description')
    if og_desc and og_desc.get('content'):
        content = clean_text(og_desc['content'])
        if content:
            return content
    
    # Try meta description (standard and variations)
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc and meta_desc.get('content'):
        content = clean_text(meta_desc['content'])
        if content:  # Use regardless of length
            return content
    
    # Try meta description with different case
    meta_desc = soup.find('meta', attrs={'name': 'Description'})
    if meta_desc and meta_desc.get('content'):
        content = clean_text(meta_desc['content'])
        if content:
            return content
    
    # Try Twitter description
    twitter_desc = soup.find('meta', attrs={'name': 'twitter:description'})
    if twitter_desc and twitter_desc.get('content'):
        content = clean_text(twitter_desc['content'])
        if content:
            return content
    
    # Try article:description
    article_desc = soup.find('meta', property='article:description')
    if article_desc and article_desc.get('content'):
        content = clean_text(article_desc['content'])
        if content:
            return content
    
    # Try to extract from first substantial paragraph
    paragraphs = soup.find_all('p')
    for p in paragraphs:
        if p and p.text:
            text = clean_text(p.text)
            if len(text) > 50:  # Only use if substantial
                return text[:300] + "..." if len(text) > 300 else text
    
    # Try h1 or h2 as fallback
    header = soup.find(['h1', 'h2'])
    if header and header.text:
        content = clean_text(header.text)
        if len(content) > 10:
            return content
    
    return "User shared article"


def extract_source(url):
    """Extract clean source name from URL"""
    domain = urlparse(url).netloc
    # Remove www. prefix and common subdomains
    domain = re.sub(r'^(www\.|m\.)', '', domain)
    # Capitalize first letter
    return domain.capitalize()


def clean_text(text):
    """Clean and normalize text content"""
    if not text:
        return ""
    
    # Remove extra whitespace and newlines
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    # Only remove site name patterns if they are at the end and preceded by common separators
    # But be more careful to preserve actual content
    if ' | ' in text and len(text.split(' | ')) > 1:
        parts = text.split(' | ')
        # Keep the longest part (likely the actual content)
        text = max(parts, key=len).strip()
    elif ' - ' in text and len(text.split(' - ')) > 1:
        parts = text.split(' - ')
        # Keep the longest part (likely the actual content)  
        text = max(parts, key=len).strip()
    
    return text