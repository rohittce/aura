/**
 * Client-side Ad Blocker
 * Blocks ads by intercepting and filtering requests
 */

(function() {
    'use strict';
    
    // Block ad domains
    const adDomains = [
        'doubleclick.net',
        'googleadservices.com',
        'googlesyndication.com',
        'google-analytics.com',
        'googletagmanager.com',
        'adservice.google',
        'ads.youtube.com',
        'advertising.com',
        'adnxs.com',
        'adsafeprotected.com',
        'advertising.com',
        'adtechus.com'
    ];
    
    // Override fetch to block ad requests
    const originalFetch = window.fetch;
    window.fetch = function(...args) {
        const url = args[0];
        if (typeof url === 'string') {
            const urlObj = new URL(url, window.location.href);
            const hostname = urlObj.hostname;
            
            // Block if domain matches ad domains
            if (adDomains.some(domain => hostname.includes(domain))) {
                console.log('Blocked ad request:', hostname);
                return Promise.reject(new Error('Ad blocked'));
            }
        }
        return originalFetch.apply(this, args);
    };
    
    // Override XMLHttpRequest to block ad requests
    const originalOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(method, url, ...rest) {
        if (typeof url === 'string') {
            try {
                const urlObj = new URL(url, window.location.href);
                const hostname = urlObj.hostname;
                
                // Block if domain matches ad domains
                if (adDomains.some(domain => hostname.includes(domain))) {
                    console.log('Blocked ad XHR request:', hostname);
                    return;
                }
            } catch (e) {
                // Invalid URL, allow it
            }
        }
        return originalOpen.apply(this, [method, url, ...rest]);
    };
    
    // Block script tags from ad domains
    const originalCreateElement = document.createElement;
    document.createElement = function(tagName, ...rest) {
        const element = originalCreateElement.apply(this, [tagName, ...rest]);
        
        if (tagName.toLowerCase() === 'script') {
            const originalSetAttribute = element.setAttribute;
            element.setAttribute = function(name, value) {
                if (name === 'src' && typeof value === 'string') {
                    try {
                        const urlObj = new URL(value, window.location.href);
                        const hostname = urlObj.hostname;
                        
                        // Block if domain matches ad domains
                        if (adDomains.some(domain => hostname.includes(domain))) {
                            console.log('Blocked ad script:', hostname);
                            return;
                        }
                    } catch (e) {
                        // Invalid URL, allow it
                    }
                }
                return originalSetAttribute.apply(this, arguments);
            };
        }
        
        return element;
    };
    
    // Block iframes from ad domains
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            mutation.addedNodes.forEach(function(node) {
                if (node.nodeType === 1) { // Element node
                    if (node.tagName === 'IFRAME' && node.src) {
                        try {
                            const urlObj = new URL(node.src, window.location.href);
                            const hostname = urlObj.hostname;
                            
                            // Block if domain matches ad domains
                            if (adDomains.some(domain => hostname.includes(domain))) {
                                console.log('Blocked ad iframe:', hostname);
                                node.remove();
                            }
                        } catch (e) {
                            // Invalid URL, allow it
                        }
                    }
                }
            });
        });
    });
    
    // Start observing
    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
    
    console.log('Ad blocker initialized');
})();

