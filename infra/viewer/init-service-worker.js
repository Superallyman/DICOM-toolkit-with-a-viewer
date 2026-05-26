navigator.serviceWorker
  ?.getRegistrations()
  .then(registrations => registrations.forEach(registration => registration.unregister()))
  .catch(() => {});
