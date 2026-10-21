"""Amazon Polly (neural) for spoken replies. The client is created once at startup."""

import time

import boto3


class Speaker:
    def __init__(self, region: str, voice_id: str) -> None:
        self.voice_id = voice_id
        self.polly = boto3.client("polly", region_name=region)

    def synthesize(self, text: str) -> tuple[bytes, int]:
        """(mp3 bytes, latency ms)."""
        started = time.perf_counter()
        resp = self.polly.synthesize_speech(
            Engine="neural", VoiceId=self.voice_id, OutputFormat="mp3", Text=text
        )
        audio = resp["AudioStream"].read()
        return audio, round((time.perf_counter() - started) * 1000)
