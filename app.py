from flask import Flask, request, jsonify
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
import re
import os
import uuid
from waitress import serve
from pathlib import Path
from dotenv import load_dotenv

app = Flask(__name__)
UPLOAD_API = "https://careainew-657352464140.us-central1.run.app/upload"
MAX_FILE_SIZE = 900_000  # bytes (to be safe under Firestore 1MB limit)
load_dotenv()
# WebScrapingAPI Configuration from environment variables
WEBSCRAPINGAPI_KEY = os.environ.get('WEBSCRAPINGAPI_KEY')
WEBSCRAPINGAPI_URL = 'https://api.webscrapingapi.com/v2'


def scrape_website_robust(url, depth=0, max_depth=1):
    """
    Scrape website content using WebScrapingAPI with automatic parameter testing
    
    Args:
        url (str): URL to scrape
        depth (int): Current depth (for compatibility)
        max_depth (int): Maximum depth (for compatibility)
        
    Returns:
        list: List of text lines from the scraped content
    """
    try:
        if not WEBSCRAPINGAPI_KEY:
            print("❌ WEBSCRAPINGAPI_KEY environment variable not set")
            return []
            
        print(f"🔍 Scraping {url} using WebScrapingAPI with robust parameter testing...")
        
        # Try different parameter combinations, starting with minimal
        parameter_sets = [
            # Minimal - just API key and URL
            {
                "api_key": WEBSCRAPINGAPI_KEY,
                "url": url
            },
            # Add JavaScript rendering
            {
                "api_key": WEBSCRAPINGAPI_KEY,
                "url": url,
                "render_js": 1
            },
            # Add timeout
            {
                "api_key": WEBSCRAPINGAPI_KEY,
                "url": url,
                "render_js": 1,
                "timeout": 10000
            },
            # Add country
            {
                "api_key": WEBSCRAPINGAPI_KEY,
                "url": url,
                "render_js": 1,
                "timeout": 10000,
                "country": "US"
            }
        ]
        
        response = None
        successful_params = None
        
        # Try each parameter set until one works
        for i, params in enumerate(parameter_sets):
            try:
                print(f"🔄 Trying parameter set {i+1}/{len(parameter_sets)}: {list(params.keys())}")
                response = requests.get(WEBSCRAPINGAPI_URL, params=params, timeout=30)
                
                if response.status_code == 200:
                    successful_params = params
                    print(f"✅ Success with parameter set: {list(params.keys())}")
                    break
                else:
                    print(f"❌ Parameter set {i+1} failed: {response.status_code}")
                    if response.text:
                        try:
                            error_response = response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text
                            print(f"Error details: {error_response}")
                        except:
                            print(f"Error details: {response.text}")
            except requests.exceptions.RequestException as e:
                print(f"❌ Network error with parameter set {i+1}: {str(e)}")
                continue
        
        # If no parameter set worked, return empty
        if not response or response.status_code != 200:
            print(f"❌ All parameter sets failed for {url}")
            return []
        
        # Parse HTML content
        html = response.text
        soup = BeautifulSoup(html, 'html.parser')
        
        # Remove unwanted elements
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "meta", "link"]):
            element.decompose()
        
        # Extract main content areas first
        main_content = soup.find(['main', 'article', 'div[role="main"]'])
        if main_content:
            content_soup = main_content
        else:
            content_soup = soup
        
        # Extract text content
        raw_text = content_soup.get_text(separator=' ', strip=True)
        
        # Normalize whitespace
        normalized_text = re.sub(r'\s+', ' ', raw_text).strip()
        
        # Split into meaningful chunks
        # First try to split by sentences
        sentences = re.split(r'(?<=[.!?])\s+', normalized_text)
        
        # Filter and clean sentences
        lines = []
        for sentence in sentences:
            sentence = sentence.strip()
            
            # Skip very short or likely navigation/footer text
            if (len(sentence) > 20 and 
                not sentence.lower().startswith(('menu', 'navigation', 'skip to', 'cookie', 'privacy')) and
                not re.match(r'^[\s\d\W]*$', sentence)):  # Skip lines with only numbers/punctuation
                lines.append(sentence)
        
        # If we didn't get good sentences, try paragraph splitting
        if len(lines) < 5:
            paragraphs = normalized_text.split('\n\n')
            lines = [p.strip() for p in paragraphs if len(p.strip()) > 50]
        
        # Final fallback: split by periods and clean
        if len(lines) < 3:
            parts = normalized_text.split('. ')
            lines = [part.strip() + '.' for part in parts if len(part.strip()) > 30]
        
        print(f"✅ Successfully extracted {len(lines)} content lines using params: {list(successful_params.keys())}")
        
        # Return first 1000 lines to avoid excessive content
        return lines[:1000]
        
    except Exception as e:
        print(f"❌ Error during scraping: {str(e)}")
        return []


def scrape_website(url, depth=0, max_depth=1):
    """
    Scrape website content using WebScrapingAPI with minimal parameters
    Falls back to robust testing if initial attempt fails
    
    Args:
        url (str): URL to scrape
        depth (int): Current depth (for compatibility)
        max_depth (int): Maximum depth (for compatibility)
        
    Returns:
        list: List of text lines from the scraped content
    """
    try:
        if not WEBSCRAPINGAPI_KEY:
            print("❌ WEBSCRAPINGAPI_KEY environment variable not set")
            return []
            
        print(f"🔍 Scraping {url} using WebScrapingAPI...")
        
        # Minimal parameters - most likely to work
        params = {
            "api_key": WEBSCRAPINGAPI_KEY,
            "url": url
        }
        
        # Make API request
        response = requests.get(WEBSCRAPINGAPI_URL, params=params, timeout=30)
        
        if response.status_code != 200:
            print(f"❌ WebScrapingAPI error: {response.status_code}")
            print(f"Response: {response.text}")
            print("🔄 Falling back to robust parameter testing...")
            return scrape_website_robust(url, depth, max_depth)
        
        # Parse HTML content
        html = response.text
        soup = BeautifulSoup(html, 'html.parser')
        
        # Remove unwanted elements
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "meta", "link"]):
            element.decompose()
        
        # Extract main content areas first
        main_content = soup.find(['main', 'article', 'div[role="main"]'])
        if main_content:
            content_soup = main_content
        else:
            content_soup = soup
        
        # Extract text content
        raw_text = content_soup.get_text(separator=' ', strip=True)
        
        # Normalize whitespace
        normalized_text = re.sub(r'\s+', ' ', raw_text).strip()
        
        # Split into meaningful chunks
        # First try to split by sentences
        sentences = re.split(r'(?<=[.!?])\s+', normalized_text)
        
        # Filter and clean sentences
        lines = []
        for sentence in sentences:
            sentence = sentence.strip()
            
            # Skip very short or likely navigation/footer text
            if (len(sentence) > 20 and 
                not sentence.lower().startswith(('menu', 'navigation', 'skip to', 'cookie', 'privacy')) and
                not re.match(r'^[\s\d\W]*$', sentence)):  # Skip lines with only numbers/punctuation
                lines.append(sentence)
        
        # If we didn't get good sentences, try paragraph splitting
        if len(lines) < 5:
            paragraphs = normalized_text.split('\n\n')
            lines = [p.strip() for p in paragraphs if len(p.strip()) > 50]
        
        # Final fallback: split by periods and clean
        if len(lines) < 3:
            parts = normalized_text.split('. ')
            lines = [part.strip() + '.' for part in parts if len(part.strip()) > 30]
        
        print(f"✅ Successfully extracted {len(lines)} content lines")
        
        # Return first 1000 lines to avoid excessive content
        return lines[:1000]
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Network error during scraping: {str(e)}")
        return []
    except Exception as e:
        print(f"❌ Error during scraping: {str(e)}")
        return []


def save_content_to_txt(lines, filename="scraped_content.txt"):
    """
    Save content lines to a text file
    
    Args:
        lines (list): List of text lines to save
        filename (str): Output filename
    """
    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        with open(filename, "w", encoding="utf-8") as f:
            for line in lines:
                # Ensure each line ends with a newline
                if not line.endswith('\n'):
                    line += '\n'
                f.write(line)
        
        print(f"💾 Content saved to {filename} ({len(lines)} lines)")
        
    except Exception as e:
        print(f"❌ Error saving content to {filename}: {str(e)}")
        raise


def split_file_by_size(original_file_path, output_dir, max_bytes=MAX_FILE_SIZE):
    """Split large files into smaller chunks"""
    part_files = []
    part_number = 1
    current_lines = []
    current_size = 0

    with open(original_file_path, "r", encoding="utf-8") as f:
        for line in f:
            encoded_line = line.encode("utf-8")
            if current_size + len(encoded_line) > max_bytes:
                part_path = os.path.join(output_dir, f"data{part_number}.txt")
                with open(part_path, "w", encoding="utf-8") as part_file:
                    part_file.writelines(current_lines)
                part_files.append(part_path)
                part_number += 1
                current_lines = []
                current_size = 0
            current_lines.append(line)
            current_size += len(encoded_line)

        # Save the last part
        if current_lines:
            part_path = os.path.join(output_dir, f"data{part_number}.txt")
            with open(part_path, "w", encoding="utf-8") as part_file:
                part_file.writelines(current_lines)
            part_files.append(part_path)

    return part_files


@app.route("/scrape", methods=["POST"])
def scrape():
    try:
        # Check if API key is configured
        if not WEBSCRAPINGAPI_KEY:
            return jsonify({
                "error": "WebScrapingAPI key not configured",
                "details": "Please set WEBSCRAPINGAPI_KEY environment variable"
            }), 500

        data = request.get_json()
        url = data.get("url")
        org_id = data.get("orgId")
        max_depth = data.get("depth", 1)
        link_id = data.get("linkId")  # Get linkId for website links
        link_name = data.get("linkName", "Unknown Website")  # Get link name

        if not url or not org_id:
            return jsonify({"error": "Both 'url' and 'orgId' are required"}), 400

        parsed_url = urlparse(url)
        if not all([parsed_url.scheme, parsed_url.netloc]):
            return jsonify({"error": "Invalid URL format"}), 400

        print(f"🔍 Starting scrape for URL: {url}")
        if link_id:
            print(f"📝 Link ID: {link_id}, Link Name: {link_name}")

        lines = scrape_website(url, depth=0, max_depth=max_depth)

        if not lines:
            print(f"⚠️ No content scraped from {url}")
            return jsonify({
                "message": "No content scraped",
                "warning": "Check URL, scraping restrictions, or WebScrapingAPI credits",
                "link_id": link_id,
                "link_name": link_name
            }), 204

        print(f"✅ Successfully scraped {len(lines)} lines from {url}")

        # Unique folder for each request (multi-user support)
        request_id = link_id if link_id else str(uuid.uuid4())
        output_folder = f"temp_uploads/{request_id}"
        Path(output_folder).mkdir(parents=True, exist_ok=True)

        # Use link name for filename if available
        base_filename = f"{link_name.replace(' ', '_')}_content" if link_name != "Unknown Website" else "scraped_content"
        original_file = os.path.join(output_folder, f"{base_filename}.txt")
        save_content_to_txt(lines, filename=original_file)

        part_files = split_file_by_size(original_file, output_folder)
        upload_responses = []

        # Build upload URL with parameters
        upload_url = f"{UPLOAD_API}?orgId={org_id}"
        if link_id:
            upload_url += f"&fileId={link_id}"  # Use linkId as fileId for AI service
            upload_url += f"&uploadId={request_id}"

        print(f"📤 Uploading to AI service: {upload_url}")

        for file_path in part_files:
            file_size = os.path.getsize(file_path)
            if file_size > MAX_FILE_SIZE:
                upload_responses.append({
                    "file": os.path.basename(file_path),
                    "status": 400,
                    "error": f"File too large after split: {file_size} bytes"
                })
                continue

            with open(file_path, "rb") as f:
                try:
                    res = requests.post(
                        upload_url,
                        files={"file": (f"{base_filename}.txt", f, "text/plain")},
                        timeout=30  # Add timeout
                    )
                    
                    upload_responses.append({
                        "file": os.path.basename(file_path),
                        "status": res.status_code,
                        "response": res.json() if res.headers.get("content-type", "").startswith("application/json") else res.text
                    })
                    
                    print(f"✅ Upload response: {res.status_code}")
                    
                except requests.exceptions.RequestException as e:
                    print(f"❌ Upload failed: {str(e)}")
                    upload_responses.append({
                        "file": os.path.basename(file_path),
                        "status": 500,
                        "error": f"Upload request failed: {str(e)}"
                    })

            # Clean up individual part file
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"⚠️ Failed to remove part file {file_path}: {e}")

        # Clean up original file and folder
        try:
            os.remove(original_file)
            os.rmdir(output_folder)
        except Exception as e:
            print(f"⚠️ Failed to clean up: {e}")

        # Check if any uploads were successful
        successful_uploads = [r for r in upload_responses if r["status"] in [200, 201, 202]]
        
        # Log the results but don't update backend status
        # The AI service will handle status updates based on embedding success
        if successful_uploads:
            print(f"✅ Successfully sent {len(successful_uploads)} file parts to AI service")
        else:
            print(f"❌ All uploads to AI service failed")

        return jsonify({
            "message": "Scraping complete. Content sent to AI service for processing.",
            "scraping_method": "WebScrapingAPI",
            "parts_uploaded": len(part_files),
            "successful_uploads": len(successful_uploads),
            "upload_responses": upload_responses,
            "sample": lines[:10],
            "total_lines": len(lines),
            "link_id": link_id,
            "link_name": link_name,
            "note": "AI service will update embedding status upon successful processing"
        })

    except Exception as e:
        error_msg = str(e)
        print(f"❌ Scraping error: {error_msg}")
        
        return jsonify({
            "error": "Scraping failed", 
            "details": error_msg,
            "link_id": link_id if 'link_id' in locals() else None,
            "link_name": link_name if 'link_name' in locals() else None
        }), 500


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    api_configured = bool(WEBSCRAPINGAPI_KEY)
    
    return jsonify({
        "status": "healthy",
        "service": "Web Scraper - WebScrapingAPI Integration",
        "version": "2.3.0",
        "description": "Scrapes content using WebScrapingAPI and sends to AI service",
        "api_integration": "WebScrapingAPI v2",
        "api_key_configured": api_configured,
        "warning": "API key not configured" if not api_configured else None
    }), 200


@app.route("/test-api", methods=["GET"])
def test_api():
    """Test WebScrapingAPI configuration"""
    try:
        if not WEBSCRAPINGAPI_KEY:
            return jsonify({
                "status": "error",
                "message": "WEBSCRAPINGAPI_KEY environment variable not set"
            }), 400
        
        # Test with a simple request using minimal parameters
        params = {
            "api_key": WEBSCRAPINGAPI_KEY,
            "url": "https://httpbin.org/get"
        }
        
        response = requests.get(WEBSCRAPINGAPI_URL, params=params, timeout=10)
        
        return jsonify({
            "status": "success" if response.status_code == 200 else "error",
            "status_code": response.status_code,
            "message": "API is working" if response.status_code == 200 else f"API error: {response.status_code}",
            "api_key_configured": True,
            "parameters_used": list(params.keys())
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"API test failed: {str(e)}",
            "api_key_configured": bool(WEBSCRAPINGAPI_KEY)
        }), 500


@app.route("/test-parameters", methods=["GET"])
def test_parameters():
    """Test different parameter combinations to find what works"""
    if not WEBSCRAPINGAPI_KEY:
        return jsonify({
            "error": "WEBSCRAPINGAPI_KEY environment variable not set"
        }), 400
    
    test_url = "https://httpbin.org/get"
    results = []
    
    # Test basic parameters first
    basic_params = {
        "api_key": WEBSCRAPINGAPI_KEY,
        "url": test_url
    }
    
    try:
        response = requests.get(WEBSCRAPINGAPI_URL, params=basic_params, timeout=10)
        results.append({
            "test": "basic",
            "status": response.status_code,
            "success": response.status_code == 200,
            "params": ["api_key", "url"]
        })
    except Exception as e:
        results.append({
            "test": "basic",
            "status": "error",
            "success": False,
            "error": str(e)
        })
    
    # Test with additional parameters one by one
    additional_params = [
        ("render_js", 1),
        ("timeout", 10000),
        ("country", "US"),
        ("device", "desktop"),
        ("wait_until", "load"),
        ("json_dom", 0)
    ]
    
    for param_name, param_value in additional_params:
        test_params = basic_params.copy()
        test_params[param_name] = param_value
        
        try:
            response = requests.get(WEBSCRAPINGAPI_URL, params=test_params, timeout=10)
            results.append({
                "test": f"with_{param_name}",
                "status": response.status_code,
                "success": response.status_code == 200,
                "params": list(test_params.keys())
            })
        except Exception as e:
            results.append({
                "test": f"with_{param_name}",
                "status": "error",
                "success": False,
                "error": str(e)
            })
    
    return jsonify({
        "message": "Parameter compatibility test completed",
        "results": results,
        "working_params": [r["params"] for r in results if r.get("success")],
        "recommended_params": results[0]["params"] if results and results[0].get("success") else []
    })


@app.route("/test-scraping", methods=["POST"])
def test_scraping():
    """Test endpoint to verify scraping functionality"""
    try:
        data = request.get_json()
        url = data.get("url", "https://example.com")
        
        if not WEBSCRAPINGAPI_KEY:
            return jsonify({
                "error": "WEBSCRAPINGAPI_KEY environment variable not set"
            }), 400
        
        lines = scrape_website(url)
        
        return jsonify({
            "message": "Test scraping completed",
            "url": url,
            "lines_extracted": len(lines),
            "sample": lines[:5] if lines else [],
            "api_status": "working" if lines else "failed"
        })
        
    except Exception as e:
        return jsonify({
            "error": "Test scraping failed",
            "details": str(e)
        }), 500


if __name__ == "__main__":
    # Check if API key is configured
    if not WEBSCRAPINGAPI_KEY:
        print("⚠️ WARNING: WEBSCRAPINGAPI_KEY environment variable not set!")
        print("Please set it using: export WEBSCRAPINGAPI_KEY='your-api-key'")
    else:
        print(f"✅ WebScrapingAPI key configured (ends with: ...{WEBSCRAPINGAPI_KEY[-4:]})")
    
    Path("temp_uploads").mkdir(exist_ok=True)
    port = int(os.environ.get("PORT", 8081))
    print(f"🚀 Starting Web Scraper with WebScrapingAPI on port {port}")
    print("📝 Note: AI service handles all embedding status updates")
    print("🔧 Version 2.3.0 - Fixed parameter compatibility issues")
    serve(app, host="0.0.0.0", port=port)