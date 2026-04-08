import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

export const WelcomeVideo = () => {
    const frame = useCurrentFrame();
    const { fps, durationInFrames, width, height } = useVideoConfig();

    const opacity = interpolate(
        frame,
        [0, 30, durationInFrames - 30, durationInFrames],
        [0, 1, 1, 0]
    );

    const scale = interpolate(
        frame,
        [0, durationInFrames],
        [0.9, 1.1]
    );

    return (
        <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", backgroundColor: "#040810", opacity, transform: `scale(${scale})` }}>
            <h1 style={{ fontSize: "80px", color: "#2ad2ff", textShadow: "0 0 20px rgba(42, 210, 255, 0.8)", fontFamily: "Inter, sans-serif", margin: 0 }}>
                ControlHub
            </h1>
            <p style={{ fontSize: "40px", color: "#edf3ff", fontFamily: "Inter, sans-serif", marginTop: 20 }}>
                Intelligent Workforce Management
            </p>
        </AbsoluteFill>
    );
};
