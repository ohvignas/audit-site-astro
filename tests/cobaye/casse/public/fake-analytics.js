document.cookie = '_ga_cobaye=GA1.1.1234567890; path=/; max-age=31536000; SameSite=Lax';
if (navigator.sendBeacon) navigator.sendBeacon('/collect', 'page=' + location.pathname);
