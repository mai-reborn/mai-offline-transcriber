# worker_transcribe.py
# Worker thread script for transcribing audio files.
# run in a separate thread by the gui application
# to allow reading the transcription progress
# sent by whisper to the standard output
import sys
import whisper
import os

# Dictionary of messages in two languages
MESSAGES = {
    "en": {
        "usage": "Usage: worker_transcribe.py <audio_file> <model_name> <output_format> [en|pl]",
        "worker_start": "Worker start. file_path={file_path}, model={model_name}, format={output_format}",
        "transcription_saved": "Transcription file saved to:",
        "done": "###DONE###"
    },
    "pl": {
        "usage": "Użycie: worker_transcribe.py <ścieżka_pliku_audio> <model_name> <output_format> [en|pl]",
        "worker_start": "Rozpoczynam worker. Ścieżka={file_path}, model={model_name}, format={output_format}",
        "transcription_saved": "Zapisano transkrypcję w pliku:",
        "done": "###KONIEC###"
    }
}

def main():
    # Check if we have at least 4 arguments:
    # 1) file_path
    # 2) model_name
    # 3) output_format
    # 4) (optional) lang = en/pl
    if len(sys.argv) < 4:
        print(MESSAGES["en"]["usage"])
        sys.exit(1)

    file_path = sys.argv[1]
    model_name = sys.argv[2]
    output_format = sys.argv[3]

    # If a 5th argument is given, use it as language code
    # otherwise, default to 'en'
    if len(sys.argv) >= 5:
        lang = sys.argv[4]
        if lang not in ("en", "pl"):
            # If something strange is provided, revert to 'en'
            lang = "en"
    else:
        lang = "en"

    # Startup message
    print(
        MESSAGES[lang]["worker_start"].format(
            file_path=file_path,
            model_name=model_name,
            output_format=output_format
        ),
        flush=True
    )

    # Load Whisper model
    model = whisper.load_model(model_name)

    # Start transcription
    result = model.transcribe(file_path, verbose=True)

    # Extract segments, prepare output path
    segments = result["segments"]
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    out_path = os.path.join(os.path.dirname(file_path), base_name + output_format)

    # Save to file
    if output_format == ".txt":
        with open(out_path, 'w', encoding='utf-8') as f:
            for seg in segments:
                text = seg['text'].strip()
                f.write(text)
                # Sprawdzenie, czy tekst kończy się na znak interpunkcyjny oznaczający koniec zdania
                if text.endswith(('.', '!', '?')):
                    f.write("\n\n")
                else:
                    f.write(" ")
    else:
        # Save in SRT format
        def format_time(seconds):
            hours, remainder = divmod(int(seconds), 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{hours:02d}:{minutes:02d}:{seconds:02d},000"

        with open(out_path, 'w', encoding='utf-8') as f:
            for i, seg in enumerate(segments, start=1):
                start_time_seg = format_time(seg['start'])
                end_time_seg = format_time(seg['end'])
                text = seg['text'].strip()
                f.write(f"{i}\n{start_time_seg} --> {end_time_seg}\n{text}\n\n")

    # Message about saved transcription
    print(f"\n{MESSAGES[lang]['transcription_saved']}\n {out_path}\n", flush=True)

    # End signal
    print(MESSAGES[lang]["done"], flush=True)

if __name__ == "__main__":
    main()