#!/usr/bin/env python3
"""
Cookie Merger for Song Downloader
Intelligently merges YouTube and YouTube Music cookie files
"""

import os
import sys
from pathlib import Path
from typing import Dict, Set, List, Tuple
from datetime import datetime

def parse_cookie_line(line: str) -> Tuple[str, Dict]:
    """Parse a single cookie line into key components"""
    parts = line.strip().split('\t')
    if len(parts) < 7:
        return None, {}
    
    return {
        'domain': parts[0],
        'flag': parts[1] == 'TRUE',
        'path': parts[2], 
        'secure': parts[3] == 'TRUE',
        'expiration': int(parts[4]) if parts[4] != '0' else 0,
        'name': parts[5],
        'value': parts[6],
        'raw_line': line.strip()
    }

def merge_cookie_files(youtube_file: Path, music_file: Path, output_file: Path):
    """Intelligently merge cookie files, preferring newer cookies"""
    
    cookies = {}  # key: (domain, name) -> cookie_dict
    
    files_to_process = []
    if youtube_file.exists():
        files_to_process.append(('YouTube', youtube_file))
    if music_file.exists():
        files_to_process.append(('YouTube Music', music_file))
    
    print(f"Merging cookies from {len(files_to_process)} files...")
    
    for source_name, file_path in files_to_process:
        print(f"  Reading {source_name}: {file_path.name}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        cookie_count = 0
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
                
            cookie = parse_cookie_line(line)
            if not cookie:
                continue
            
            key = (cookie['domain'], cookie['name'])
            
            # If we already have this cookie, prefer the one with later expiration
            if key in cookies:
                existing = cookies[key]
                
                # Prefer non-zero expiration over zero expiration
                if existing['expiration'] == 0 and cookie['expiration'] > 0:
                    cookies[key] = cookie
                elif cookie['expiration'] == 0 and existing['expiration'] > 0:
                    pass  # Keep existing
                elif cookie['expiration'] > existing['expiration']:
                    cookies[key] = cookie
                # If same expiration, prefer longer value (often more recent)
                elif cookie['expiration'] == existing['expiration']:
                    if len(cookie['value']) > len(existing['value']):
                        cookies[key] = cookie
            else:
                cookies[key] = cookie
                
            cookie_count += 1
        
        print(f"    Found {cookie_count} cookies")
    
    # Write combined file
    print(f"Writing combined file: {output_file}")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        # Write header
        f.write("# Netscape HTTP Cookie File\n")
        f.write("# https://curl.haxx.se/rfc/cookie_spec.html\n") 
        f.write("# This is a generated file! Do not edit.\n")
        f.write("#\n")
        f.write("# Combined YouTube & YouTube Music Cookie File\n")
        f.write("# Intelligently merged with preference for newer cookies\n")
        f.write(f"# Generated: {datetime.now().isoformat()}\n")
        f.write("#\n")
        f.write("\n")
        
        # Sort cookies by domain, then by name
        sorted_cookies = sorted(cookies.values(), key=lambda x: (x['domain'], x['name']))
        
        for cookie in sorted_cookies:
            f.write(cookie['raw_line'] + '\n')
    
    print(f"Successfully merged {len(cookies)} unique cookies")
    
    # Show domains
    domains = set(cookie['domain'] for cookie in cookies.values())
    print(f"Domains included: {sorted(domains)}")
    
    return len(cookies)

def main():
    """Main function"""
    cookies_dir = Path(__file__).parent
    
    youtube_file = cookies_dir / 'www.youtube.com_cookies.txt'
    music_file = cookies_dir / 'music.youtube.com_cookies.txt'
    output_file = cookies_dir / 'cookies.txt'
    
    print("🍪 Cookie Merger for Song Downloader")
    print("=" * 50)
    
    if not youtube_file.exists() and not music_file.exists():
        print("❌ No source cookie files found!")
        print(f"Expected files:")
        print(f"  - {youtube_file}")
        print(f"  - {music_file}")
        return 1
    
    try:
        cookie_count = merge_cookie_files(youtube_file, music_file, output_file)
        
        print("\n✅ Cookie merge completed successfully!")
        print(f"📄 Output file: {output_file}")
        print(f"📊 Total cookies: {cookie_count}")
        
        # Backup original files
        if youtube_file.exists():
            backup_file = youtube_file.with_suffix('.txt.backup')
            youtube_file.rename(backup_file)
            print(f"📦 Backed up YouTube cookies to: {backup_file}")
            
        if music_file.exists():
            backup_file = music_file.with_suffix('.txt.backup')
            music_file.rename(backup_file)
            print(f"📦 Backed up Music cookies to: {backup_file}")
        
        print("\n🚀 Your application will now use the combined cookie file!")
        
    except Exception as e:
        print(f"❌ Error merging cookies: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())