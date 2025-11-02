#!/usr/bin/env python3
"""
Audio Processor for Lightsaber Sound Files
Optimizes WAV files for CircuitPython PWM audio output

Requirements:
    pip install pydub numpy

Also requires ffmpeg installed on system:
    - Windows: Download from https://ffmpeg.org/download.html
    - Mac: brew install ffmpeg
    - Linux: sudo apt-get install ffmpeg

Usage:
    python audio_processor.py sounds/0on.wav --volumes 30 60 100
    python audio_processor.py sounds/ --all --volumes 30 60 100
"""

import argparse
import os
import sys
from pathlib import Path

try:
    from pydub import AudioSegment
    from pydub.effects import normalize
    import numpy as np
except ImportError:
    print("ERROR: Required packages not installed")
    print("Please run: pip install pydub numpy")
    sys.exit(1)

# CircuitPython audio specifications
TARGET_SAMPLE_RATE = 22050
TARGET_CHANNELS = 1  # Mono
TARGET_BIT_DEPTH = 16
FADE_IN_MS = 10  # 10ms fade in to prevent click
FADE_OUT_MS = 50  # 50ms fade out to prevent pop


def analyze_audio(file_path):
    """Analyze audio file and print specifications."""
    print(f"\n📊 Analyzing: {file_path}")
    print("=" * 60)

    audio = AudioSegment.from_wav(file_path)

    print(f"Sample Rate:     {audio.frame_rate} Hz")
    print(f"Channels:        {audio.channels} ({'Stereo' if audio.channels == 2 else 'Mono'})")
    print(f"Sample Width:    {audio.sample_width} bytes ({audio.sample_width * 8}-bit)")
    print(f"Duration:        {len(audio) / 1000:.2f} seconds")
    print(f"Frame Count:     {audio.frame_count()}")
    print(f"RMS (loudness):  {audio.rms:.2f}")
    print(f"Max dBFS:        {audio.max_dBFS:.2f} dB")

    # Check if optimization needed
    issues = []
    if audio.frame_rate != TARGET_SAMPLE_RATE:
        issues.append(f"❌ Sample rate should be {TARGET_SAMPLE_RATE} Hz")
    else:
        print(f"✅ Sample rate correct")

    if audio.channels != TARGET_CHANNELS:
        issues.append(f"❌ Should be mono ({TARGET_CHANNELS} channel)")
    else:
        print(f"✅ Mono audio correct")

    if audio.sample_width * 8 != TARGET_BIT_DEPTH:
        issues.append(f"❌ Should be {TARGET_BIT_DEPTH}-bit")
    else:
        print(f"✅ Bit depth correct")

    if audio.max_dBFS > -1:
        issues.append(f"⚠️  Audio may clip (peak at {audio.max_dBFS:.1f} dB, should be < -1 dB)")
    else:
        print(f"✅ Levels good (peak at {audio.max_dBFS:.1f} dB)")

    if issues:
        print("\n⚠️  Issues found:")
        for issue in issues:
            print(f"  {issue}")
    else:
        print("\n✅ File is optimally formatted!")

    return audio


def remove_dc_offset(audio):
    """Remove DC offset from audio."""
    print("  🔧 Removing DC offset...")

    # Convert to numpy array
    samples = np.array(audio.get_array_of_samples())

    # Calculate and remove DC offset
    dc_offset = np.mean(samples)
    samples = samples - dc_offset

    # Convert back to AudioSegment
    audio = audio._spawn(samples.tobytes())
    return audio


def optimize_audio(audio, target_volume_percent=100):
    """Optimize audio for CircuitPython."""
    print(f"  🎵 Optimizing audio (target volume: {target_volume_percent}%)...")

    # Convert to mono if stereo
    if audio.channels > 1:
        print("    → Converting to mono")
        audio = audio.set_channels(1)

    # Resample if needed
    if audio.frame_rate != TARGET_SAMPLE_RATE:
        print(f"    → Resampling to {TARGET_SAMPLE_RATE} Hz")
        audio = audio.set_frame_rate(TARGET_SAMPLE_RATE)

    # Set bit depth
    if audio.sample_width != TARGET_BIT_DEPTH // 8:
        print(f"    → Converting to {TARGET_BIT_DEPTH}-bit")
        audio = audio.set_sample_width(TARGET_BIT_DEPTH // 8)

    # Normalize to -1dBFS (prevent clipping while maximizing volume)
    print("    → Normalizing to -1 dBFS")
    audio = normalize(audio, headroom=1.0)

    # Apply target volume
    if target_volume_percent != 100:
        print(f"    → Applying volume: {target_volume_percent}%")
        # Convert percentage to dB
        # 50% = -6dB, 30% = -10dB, etc.
        db_change = 20 * np.log10(target_volume_percent / 100)
        audio = audio + db_change

    # Remove DC offset
    audio = remove_dc_offset(audio)

    # Apply fade in/out to prevent clicks
    print(f"    → Adding fade in ({FADE_IN_MS}ms) / out ({FADE_OUT_MS}ms)")
    audio = audio.fade_in(FADE_IN_MS).fade_out(FADE_OUT_MS)

    return audio


def process_file(input_path, output_dir=None, volume_levels=None):
    """Process a single audio file."""
    if volume_levels is None:
        volume_levels = [100]

    input_path = Path(input_path)

    if not input_path.exists():
        print(f"❌ File not found: {input_path}")
        return False

    if input_path.suffix.lower() != '.wav':
        print(f"❌ Not a WAV file: {input_path}")
        return False

    # Analyze original
    print(f"\n{'=' * 60}")
    print(f"🎵 Processing: {input_path.name}")
    print(f"{'=' * 60}")

    try:
        audio = analyze_audio(input_path)
    except Exception as e:
        print(f"❌ Error analyzing file: {e}")
        return False

    # Set output directory
    if output_dir is None:
        output_dir = input_path.parent / "optimized"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Process at each volume level
    success_count = 0
    for volume_percent in volume_levels:
        try:
            # Optimize audio
            optimized = optimize_audio(audio, volume_percent)

            # Generate output filename
            stem = input_path.stem
            if len(volume_levels) > 1:
                # Add volume suffix
                if volume_percent <= 30:
                    volume_name = "quiet"
                elif volume_percent <= 60:
                    volume_name = "medium"
                else:
                    volume_name = "loud"
                output_filename = f"{stem}_{volume_name}.wav"
            else:
                output_filename = f"{stem}_optimized.wav"

            output_path = output_dir / output_filename

            # Export
            print(f"\n  💾 Exporting: {output_filename}")
            optimized.export(
                output_path,
                format="wav",
                parameters=[
                    "-acodec", "pcm_s16le",  # 16-bit PCM
                    "-ar", str(TARGET_SAMPLE_RATE),  # Sample rate
                    "-ac", str(TARGET_CHANNELS)  # Mono
                ]
            )

            # Verify output
            exported = AudioSegment.from_wav(output_path)
            print(f"    ✅ Created: {output_path}")
            print(f"       Size: {output_path.stat().st_size / 1024:.1f} KB")
            print(f"       Duration: {len(exported) / 1000:.2f}s")
            print(f"       Peak: {exported.max_dBFS:.1f} dBFS")

            success_count += 1

        except Exception as e:
            print(f"    ❌ Error processing at {volume_percent}%: {e}")

    print(f"\n{'=' * 60}")
    print(f"✅ Successfully processed {success_count}/{len(volume_levels)} volume levels")
    print(f"{'=' * 60}\n")

    return success_count > 0


def process_directory(input_dir, output_dir=None, volume_levels=None):
    """Process all WAV files in a directory."""
    input_dir = Path(input_dir)

    if not input_dir.is_dir():
        print(f"❌ Not a directory: {input_dir}")
        return False

    # Find all WAV files
    wav_files = list(input_dir.glob("*.wav"))
    if not wav_files:
        print(f"❌ No WAV files found in: {input_dir}")
        return False

    print(f"\n🔍 Found {len(wav_files)} WAV files")

    success_count = 0
    for wav_file in wav_files:
        if process_file(wav_file, output_dir, volume_levels):
            success_count += 1

    print(f"\n{'=' * 60}")
    print(f"🎉 COMPLETE: Processed {success_count}/{len(wav_files)} files")
    print(f"{'=' * 60}\n")

    return success_count > 0


def main():
    parser = argparse.ArgumentParser(
        description="Optimize WAV files for CircuitPython lightsaber audio",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process single file at 100% volume
  python audio_processor.py sounds/0on.wav

  # Process single file at multiple volumes
  python audio_processor.py sounds/0on.wav --volumes 30 60 100

  # Process all files in directory
  python audio_processor.py sounds/ --all --volumes 30 60 100

  # Analyze only (no processing)
  python audio_processor.py sounds/0on.wav --analyze

  # Custom output directory
  python audio_processor.py sounds/ --all --output optimized_sounds/
        """
    )

    parser.add_argument(
        "input",
        help="Input WAV file or directory"
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all WAV files in input directory"
    )

    parser.add_argument(
        "--volumes",
        type=int,
        nargs="+",
        default=[100],
        help="Volume levels to generate (e.g., 30 60 100)"
    )

    parser.add_argument(
        "--output", "-o",
        help="Output directory (default: input_dir/optimized)"
    )

    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Only analyze file(s), don't process"
    )

    args = parser.parse_args()

    # Validate volumes
    for vol in args.volumes:
        if not 1 <= vol <= 100:
            print(f"❌ Volume must be between 1-100, got: {vol}")
            sys.exit(1)

    print("=" * 60)
    print("🎵 Lightsaber Audio Processor")
    print("=" * 60)
    print(f"Target: {TARGET_SAMPLE_RATE}Hz, {TARGET_BIT_DEPTH}-bit, Mono")
    print(f"Volumes: {args.volumes}")
    print("=" * 60)

    input_path = Path(args.input)

    # Analyze only mode
    if args.analyze:
        if input_path.is_file():
            analyze_audio(input_path)
        elif input_path.is_dir():
            for wav_file in input_path.glob("*.wav"):
                analyze_audio(wav_file)
        else:
            print(f"❌ Not found: {input_path}")
            sys.exit(1)
        return

    # Process mode
    if input_path.is_file():
        success = process_file(input_path, args.output, args.volumes)
    elif input_path.is_dir() and args.all:
        success = process_directory(input_path, args.output, args.volumes)
    elif input_path.is_dir():
        print(f"❌ {input_path} is a directory. Use --all to process all files")
        sys.exit(1)
    else:
        print(f"❌ Not found: {input_path}")
        sys.exit(1)

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
