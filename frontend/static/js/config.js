const config = {
    getBackendURL: function() {
        return window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
            ? "http://localhost:8080"
            : "https://strim-production.up.railway.app";
    },
    
    getAppURL: function() {
        return window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
            ? "http://localhost:3000" 
            : "https://strimrun.vercel.app";
    }
};