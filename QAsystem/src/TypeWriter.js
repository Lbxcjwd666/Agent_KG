import React, { useState, useEffect, useRef } from 'react';

const CHARS_PER_FRAME = 4;
const FRAME_INTERVAL = 16; // ~60fps

const TypeWriter = ({ text, speed = 30 }) => {
    const [displayedText, setDisplayedText] = useState('');
    const rafRef = useRef(null);
    const indexRef = useRef(0);
    const lastTimeRef = useRef(0);

    useEffect(() => {
        indexRef.current = 0;
        lastTimeRef.current = 0;
        setDisplayedText('');

        const charsPerTick = Math.max(1, Math.floor(speed / 10));

        const animate = (timestamp) => {
            if (timestamp - lastTimeRef.current >= FRAME_INTERVAL) {
                lastTimeRef.current = timestamp;
                indexRef.current += charsPerTick;
                const end = indexRef.current;
                if (end >= text.length) {
                    setDisplayedText(text);
                    return;
                }
                setDisplayedText(text.substring(0, end));
            }
            rafRef.current = requestAnimationFrame(animate);
        };

        rafRef.current = requestAnimationFrame(animate);

        return () => {
            if (rafRef.current) {
                cancelAnimationFrame(rafRef.current);
            }
        };
    }, [text, speed]);

    return <span>{displayedText}</span>;
};

export default TypeWriter;
