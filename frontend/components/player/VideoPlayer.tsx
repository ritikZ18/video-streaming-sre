"use client";

import { useEffect, useRef } from "react";
import Hls from "hls.js";

type VideoPlayerProps = {
  src: string | null;
};

export function VideoPlayer({ src }: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const hlsRef = useRef<Hls | null>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !src) return;

    if (video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = src;
      return;
    }

    if (Hls.isSupported()) {
      const hls = new Hls({
        enableWorker: true,
      });
      hlsRef.current = hls;
      hls.loadSource(src);
      hls.attachMedia(video);

      return () => {
        hls.destroy();
        hlsRef.current = null;
      };
    }
  }, [src]);

  return (
    <div className="aspect-video w-full overflow-hidden rounded-2xl bg-black">
      <video
        ref={videoRef}
        controls
        className="h-full w-full bg-black"
        poster=""
      />
    </div>
  );
}

