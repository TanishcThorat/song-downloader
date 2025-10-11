# Cookie Files for yt-dlp

This directory contains cookie files used by yt-dlp for authentication with various services, particularly YouTube Music.

## 🚀 Quick Setup

**Automated Helper:**
```bash
cd src
python setup_cookies.py
# Or on Windows, double-click: setup_cookies.bat
```

**Manual Setup (Recommended - Combined File):**
1. Log into **both** YouTube AND YouTube Music in your browser
2. Export cookies using a browser extension for ALL sites
3. Save as `cookies.txt` in this directory (single combined file)
4. Verify with the API endpoint: `/api/cookies/status`

**Alternative (Separate Files):**
- `youtube_music.txt` - YouTube Music only
- `youtube.txt` - YouTube only

## 🔧 How to Generate Cookie Files

### Method 1: Browser Extension (Recommended)
1. **Install Extension:**
   - Chrome: "Get cookies.txt LOCALLY" or "cookies.txt"
   - Firefox: "cookies.txt" extension
   
2. **Login to Both Services:**
   - Visit [YouTube](https://youtube.com) and log in
   - Visit [YouTube Music](https://music.youtube.com) and log in (same browser session)
   
3. **Export Combined Cookies:**
   - Click the extension icon
   - Select "Export ALL cookies" (not just current site)
   - Ensure it includes cookies from: youtube.com, music.youtube.com, google.com
   - Save as `cookies.txt` in this cookies directory

### Method 2: Using yt-dlp Built-in Function
```bash
# Extract cookies from Chrome
yt-dlp --cookies-from-browser chrome --print-json "https://music.youtube.com" > /dev/null

# Extract cookies from Firefox
yt-dlp --cookies-from-browser firefox --print-json "https://music.youtube.com" > /dev/null
```

### Method 3: Manual Export from Browser Developer Tools
1. Open YouTube Music in your browser and log in
2. Press F12 to open Developer Tools
3. Go to **Application/Storage** tab → **Cookies** → **https://music.youtube.com**
4. Right-click and "Export" or manually copy cookies
5. Convert to Netscape format (see example file)

### Method 4: Chrome Settings Export
1. Visit `chrome://settings/cookies`
2. Search for "music.youtube.com"
3. Export cookies
4. Convert to Netscape format

## 📁 File Structure

```
cookies/
├── README.md                    # This file
├── cookies_example.txt          # Combined example format (committed)
├── youtube_music_example.txt    # Old example format (committed)
├── cookies.txt                  # Combined cookies - PREFERRED (gitignored)
├── youtube_music.txt           # YouTube Music only (gitignored)
└── youtube.txt                 # YouTube only (gitignored)
```

**Recommended:** Use `cookies.txt` with cookies from both YouTube and YouTube Music for best compatibility.

## 📋 Cookie File Format

Cookie files must be in **Netscape format**. A combined file should include cookies from multiple domains:

```
# Netscape HTTP Cookie File
# Domain              Flag  Path  Secure  Expiration  Name            Value
.youtube.com          TRUE  /     TRUE    1740000000  YSC             token_here
music.youtube.com     FALSE /     TRUE    1740000000  session_token   music_token
.google.com           TRUE  /     TRUE    1740000000  SID             google_sid
```

**Key Domains to Include:**
- `.youtube.com` - YouTube main cookies
- `music.youtube.com` - YouTube Music specific
- `.google.com` - Google authentication
- `.googlevideo.com` - Video streaming

See `cookies_example.txt` for the complete format.

## ✅ Verification

**Check Status via API:**
```bash
curl http://localhost:8000/api/cookies/status
```

**Check Status via Script:**
```bash
python src/setup_cookies.py
```

**Health Check:**
```bash
curl http://localhost:8000/health
```

## 🔒 Security Notes

⚠️  **Important Security Considerations:**
- Cookie files contain **sensitive authentication data**
- Never commit actual cookie files to version control
- Cookie files are automatically excluded by `.gitignore`
- Regenerate cookies periodically for security
- Don't share cookie files with others
- Cookies may contain session tokens and personal info

## 🔄 Maintenance

**Regular Tasks:**
- Regenerate cookies monthly for security
- Check cookie expiration dates
- Update cookies if downloads start failing
- Monitor authentication status via `/api/cookies/status`

**Troubleshooting:**
1. Verify you're logged into YouTube Music in your browser
2. Check that the cookie file isn't the example template
3. Ensure cookies are in correct Netscape format
4. Re-export cookies if they're old or expired
5. Check application logs for cookie-related errors

## 🚀 Benefits of Using Cookies

With properly configured cookies:
- Higher download success rates
- Access to region-locked content  
- Better search results from YouTube Music
- Reduced rate limiting
- Access to user-specific playlists (future feature)

## 🆘 Support

If you're having issues:
1. Run the cookie setup helper: `python src/setup_cookies.py`
2. Check the API status: `GET /api/cookies/status`  
3. Review application logs for detailed error messages
4. Ensure you're logged into YouTube Music in the same browser used for export

## 📚 Additional Resources

- [yt-dlp Cookie Documentation](https://github.com/yt-dlp/yt-dlp#authentication-with-netrc-file)
- [Netscape Cookie Format Specification](http://www.cookiecentral.com/faq/#3.5)
- [YouTube Music](https://music.youtube.com) - Login here before exporting cookies