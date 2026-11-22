import { useId, useState } from 'react';

export default function ReviewAbout() {
  const id = useId();
  const [open, setOpen] = useState(false);

  return (
    <div className="review-about">
      <button
        type="button"
        className="text-button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
      >
        How it works
      </button>
      <p id={id} hidden={!open}>
        The app picks out the main reasons you own the stock and splits each into checks.
        It searches the four most recent earnings reports and any matching calls for each check. Groq reads the relevant passages and summarizes what
        directly supports or challenges your thesis for each period.
      </p>
    </div>
  );
}
