// StudyList.tsx
import React, { useEffect, useState } from 'react';
import { API_URL } from '../../src/utils/env';

interface Study {
  StudyInstanceUID: string;
  PatientName: string;
  StudyDate: string;
  StudyDescription?: string;
}

interface Props {
  onSelect: (studyUID: string) => void;
}

export default function StudyList({ onSelect }: Props) {
  const [studies, setStudies] = useState<Study[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_URL}/studies`)
      .then(res => res.json())
      .then(data => {
        setStudies(data);
        setLoading(false);
      })
      .catch(err => {
        setError('Failed to load studies');
        setLoading(false);
      });
  }, []);

  if (loading) return <p>Loading studies...</p>;
  if (error) return <p className="text-red-500">{error}</p>;

  return (
    <div className="mb-4">
      <h2 className="text-lg font-semibold">Available Studies</h2>
      <ul className="space-y-2">
        {studies.map(study => (
          <li key={study.StudyInstanceUID} className="border p-2 rounded cursor-pointer hover:bg-gray-100" onClick={() => onSelect(study.StudyInstanceUID)}>
            <p className="font-bold">{study.PatientName}</p>
            <p className="text-sm text-gray-600">{study.StudyDate} - {study.StudyDescription || 'No Description'}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
