import React from 'react';

export default function VideoPanel({ frame, active }) {
  if (!active || !frame) {
    return (
      <div className="video-placeholder">
        {active ? 'Waiting for frames…' : 'Start a session to see the live feed'}
      </div>
    );
  }
  return <img className="video-frame" src={frame} alt="Live classroom feed" />;
}
