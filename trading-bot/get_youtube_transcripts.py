#!/usr/bin/env python3
"""
Get YouTube transcripts for TTrades videos
"""
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound, VideoUnavailable
import json
from pathlib import Path

VIDEOS = [
    {
        "id": "sUxpK1o5ELQ",
        "title": "TTrades Fractal Model Masterclass (assumed)"
    },
    {
        "id": "jHFGdZq0lsw", 
        "title": "TTrades Fractal Trading Strategy"
    }
]


def get_transcript(video_id: str) -> dict:
    """Get transcript for a single video"""
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        
        # Combine into full text
        full_text = " ".join([entry['text'] for entry in transcript])
        
        return {
            "success": True,
            "video_id": video_id,
            "entries_count": len(transcript),
            "transcript": transcript,
            "full_text": full_text
        }
    except TranscriptsDisabled:
        return {
            "success": False,
            "video_id": video_id,
            "error": "Transcripts are disabled for this video"
        }
    except NoTranscriptFound:
        return {
            "success": False, 
            "video_id": video_id,
            "error": "No transcript found for this video"
        }
    except VideoUnavailable:
        return {
            "success": False,
            "video_id": video_id,
            "error": "Video is unavailable"
        }
    except Exception as e:
        return {
            "success": False,
            "video_id": video_id,
            "error": str(e)
        }


def main():
    output_dir = Path("data/transcripts")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    results = []
    
    for video in VIDEOS:
        print(f"\nFetching transcript for: {video['title']}")
        print(f"  Video ID: {video['id']}")
        
        result = get_transcript(video['id'])
        result['title'] = video['title']
        results.append(result)
        
        if result['success']:
            print(f"  SUCCESS: {result['entries_count']} entries, {len(result['full_text'])} chars")
            
            # Save full text
            text_path = output_dir / f"{video['id']}_transcript.txt"
            with open(text_path, 'w') as f:
                f.write(f"Title: {video['title']}\n")
                f.write(f"Video ID: {video['id']}\n")
                f.write(f"URL: https://youtube.com/watch?v={video['id']}\n")
                f.write("=" * 60 + "\n\n")
                f.write(result['full_text'])
            print(f"  Saved to: {text_path}")
        else:
            print(f"  FAILED: {result['error']}")
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    success = sum(1 for r in results if r['success'])
    print(f"Successful: {success}/{len(results)}")
    
    for r in results:
        status = "✓" if r['success'] else "✗"
        print(f"  {status} {r['title']}: {r.get('error', 'OK')}")
    
    return results


if __name__ == "__main__":
    main()
