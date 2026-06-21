import React, { useEffect, useState } from 'react';
import { api } from '../api';
import ProfileView from './ProfileView.jsx';

export default function StudentPortal({ pushToast }) {
  const [profile, setProfile] = useState(null);

  useEffect(() => {
    let cancelled = false;
    const load = () => api.myStudentProfile()
      .then((p) => { if (!cancelled) setProfile(p); })
      .catch((e) => { if (!cancelled) pushToast(e.message, 'error'); });
    load();
    const id = setInterval(load, 30000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  return (
    <main>
      <h2 className="portal-title">
        {profile ? `Welcome, ${profile.name}` : 'My profile'}
      </h2>
      <ProfileView profile={profile} />
    </main>
  );
}
