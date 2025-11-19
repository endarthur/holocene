// ==UserScript==
// @name         Mercado Livre Favorites Exporter
// @namespace    http://tampermonkey.net/
// @version      1.0
// @description  Export all your Mercado Livre favorites to JSON for Holocene
// @author       You + Claude
// @match        https://myaccount.mercadolivre.com.br/bookmarks/list*
// @match        https://myaccount.mercadolivre.com.br/bookmarks/*
// @grant        none
// ==/UserScript==

(function() {
    'use strict';

    // Storage for collected favorites across pages
    let allFavorites = [];
    let isCollecting = false;
    let currentPage = 1;
    let totalPages = 1;
    let lastCollectedPage = 0;  // Safety: track last page to prevent infinite loops

    // Extract favorites from current page
    function extractFavoritesFromPage() {
        try {
            // Find the __PRELOADED_STATE__ script
            const scripts = document.querySelectorAll('script');
            let preloadedState = null;

            for (let script of scripts) {
                const content = script.textContent;
                if (content.includes('__PRELOADED_STATE__')) {
                    const match = content.match(/__PRELOADED_STATE__\s*=\s*({.*?});/s);
                    if (match) {
                        preloadedState = JSON.parse(match[1]);
                        break;
                    }
                }
            }

            if (!preloadedState) {
                console.error('Could not find __PRELOADED_STATE__');
                return [];
            }

            // Parse the polycards structure
            const elements = preloadedState.initialState?.elements || {};
            const polycards = elements.polycards || [];

            console.log(`Found ${polycards.length} items on this page`);

            const favorites = [];

            for (let polycard of polycards) {
                const metadata = polycard.metadata || {};
                const components = polycard.components || [];

                // Extract data from components
                let title = null;
                let price = null;
                let currency = null;
                let condition = null;

                for (let component of components) {
                    const compType = component.type;

                    if (compType === 'title') {
                        title = component.title?.text;
                    } else if (compType === 'price') {
                        const priceData = component.price?.current_price || {};
                        price = priceData.value;
                        currency = priceData.currency;
                    } else if (compType === 'attributes') {
                        const attrs = component.attributes || [];
                        for (let attr of attrs) {
                            if (attr.id === 'ITEM_CONDITION') {
                                condition = attr.text;
                            }
                        }
                    }
                }

                // Build full URL
                const urlBase = metadata.url || '';
                const urlParams = metadata.url_params || '';
                const permalink = urlBase ? `https://${urlBase}${urlParams}` : null;

                const pictures = polycard.pictures?.pictures || [];
                const thumbnailId = pictures[0]?.id || null;

                favorites.push({
                    item_id: metadata.id,
                    bookmark_id: metadata.bookmarks_id,
                    variation_id: metadata.variation_id,
                    title: title,
                    price: price,
                    currency: currency,
                    permalink: permalink,
                    condition: condition,
                    thumbnail_id: thumbnailId,
                    collected_at: new Date().toISOString()
                });
            }

            return favorites;

        } catch (error) {
            console.error('Error extracting favorites:', error);
            return [];
        }
    }

    // Get current page number and total pages
    function getPaginationInfo() {
        // Method 1: Check URL parameters for current page
        const urlParams = new URLSearchParams(window.location.search);
        const page = parseInt(urlParams.get('page')) || 1;

        // Method 2: Parse pagination links to find highest page number (MOST RELIABLE)
        const paginationLinks = document.querySelectorAll('.andes-pagination a[href*="page="]');
        console.log(`Found ${paginationLinks.length} pagination links`);

        if (paginationLinks.length > 0) {
            let maxPage = 1;
            paginationLinks.forEach(link => {
                const match = link.href.match(/page=(\d+)/);
                if (match) {
                    const pageNum = parseInt(match[1]);
                    console.log(`  Found link to page ${pageNum}`);
                    if (pageNum > maxPage) {
                        maxPage = pageNum;
                    }
                }
            });

            if (maxPage > 1) {
                console.log(`✓ Detected ${maxPage} total pages from pagination links`);
                return {
                    current: page,
                    total: maxPage
                };
            }
        }

        // Method 3: Look for pagination text in page
        const pageText = document.body.innerText;
        const match = pageText.match(/página\s+(\d+)\s+de\s+(\d+)/i);
        if (match) {
            console.log(`✓ Found pagination text: ${match[0]}`);
            return {
                current: parseInt(match[1]),
                total: parseInt(match[2])
            };
        }

        // Fallback: use page from URL
        console.log(`⚠ Could not detect total pages, using fallback`);
        return { current: page, total: page };
    }

    // Find the "next page" button
    function findNextButton() {
        const nextSelectors = [
            '.andes-pagination__button--next a',  // Primary selector for ML
            'a[title="Seguinte"]',                // Portuguese "Next"
            'a[title*="Seguinte"]',
            'a[aria-label*="Siguiente"]',         // Spanish fallback
            'a[aria-label*="Next"]',              // English fallback
            'a[aria-label*="Próxima"]',           // Alternative Portuguese
            'a[title*="próxima"]',
            '[class*="pagination"] a[class*="next"]',
            '.andes-pagination__button--next',
            'button[aria-label*="Next"]',
            'button[aria-label*="Próxima"]'
        ];

        for (let selector of nextSelectors) {
            const button = document.querySelector(selector);
            if (button && !button.classList.contains('disabled') && !button.hasAttribute('disabled')) {
                return button;
            }
        }

        return null;
    }

    // Navigate to next page
    function goToNextPage() {
        const nextButton = findNextButton();

        if (nextButton) {
            console.log('Found next button, trying multiple click methods...');

            // Try multiple ways to click
            try {
                // Method 1: Native click
                nextButton.click();
            } catch (e) {
                console.log('Native click failed:', e);
            }

            try {
                // Method 2: Dispatch mouse event
                const clickEvent = new MouseEvent('click', {
                    view: window,
                    bubbles: true,
                    cancelable: true
                });
                nextButton.dispatchEvent(clickEvent);
            } catch (e) {
                console.log('MouseEvent dispatch failed:', e);
            }

            try {
                // Method 3: Get href and navigate manually
                if (nextButton.href) {
                    console.log('Using href navigation:', nextButton.href);
                    window.location.href = nextButton.href;
                    return true;
                }
            } catch (e) {
                console.log('href navigation failed:', e);
            }
        }

        // Fallback: construct URL manually
        console.log('Using URL fallback method...');
        const urlParams = new URLSearchParams(window.location.search);
        const currentPage = parseInt(urlParams.get('page')) || 1;
        const nextPage = currentPage + 1;

        console.log(`Navigating from page ${currentPage} to ${nextPage}`);

        // Navigate to next page
        urlParams.set('page', nextPage);
        window.location.href = window.location.pathname + '?' + urlParams.toString();
        return true;
    }

    // Download JSON file
    function downloadJSON(data, filename) {
        const json = JSON.stringify(data, null, 2);
        const blob = new Blob([json], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    // Export current page only
    function exportCurrentPage() {
        const favorites = extractFavoritesFromPage();
        if (favorites.length === 0) {
            alert('No favorites found on this page!');
            return;
        }

        const filename = `mercadolivre_favorites_page${currentPage}_${new Date().toISOString().split('T')[0]}.json`;
        downloadJSON(favorites, filename);
        updateButton(`✓ Exported ${favorites.length} items from page ${currentPage}`);
        setTimeout(() => updateButton(), 2000);
    }

    // Auto-collect all pages
    async function autoCollectAllPages() {
        if (isCollecting) return;

        isCollecting = true;
        allFavorites = [];
        lastCollectedPage = 0;  // Reset safety tracker

        const pagination = getPaginationInfo();
        totalPages = pagination.total;
        currentPage = pagination.current;

        console.log(`Starting collection: page ${currentPage}, detected ${totalPages} total pages`);
        updateButton(`Collecting page ${currentPage}/${totalPages}...`);

        lastCollectedPage = currentPage;

        // Collect current page
        const currentFavorites = extractFavoritesFromPage();
        allFavorites.push(...currentFavorites);

        console.log(`Collected ${currentFavorites.length} items from page ${currentPage}`);

        // Check if we're done (current page >= total pages)
        if (currentPage >= totalPages) {
            console.log(`Reached page ${currentPage}/${totalPages} - collection complete`);
            finishCollection();
            return;
        }

        // Store progress in localStorage
        localStorage.setItem('meli_collecting', 'true');
        localStorage.setItem('meli_collected_data', JSON.stringify(allFavorites));
        localStorage.setItem('meli_current_page', currentPage.toString());
        localStorage.setItem('meli_total_pages', totalPages.toString());

        // Go to next page
        setTimeout(() => {
            goToNextPage();
        }, 1000); // Wait 1 second before navigating
    }

    // Finish collection and download
    function finishCollection() {
        isCollecting = false;
        lastCollectedPage = 0;  // Reset safety tracker

        const totalItems = allFavorites.length;
        const pagesCollected = currentPage;
        const filename = `mercadolivre_all_favorites_${new Date().toISOString().split('T')[0]}.json`;

        downloadJSON(allFavorites, filename);

        // Clean up localStorage
        localStorage.removeItem('meli_collecting');
        localStorage.removeItem('meli_collected_data');
        localStorage.removeItem('meli_current_page');
        localStorage.removeItem('meli_total_pages');

        updateButton(`✓ Downloaded ${totalItems} total favorites!`);

        alert(`✓ Successfully exported ${totalItems} favorites from ${pagesCollected} page(s)!\n\nFile: ${filename}\n\nNow run:\nholo mercadolivre import-json ${filename}`);

        setTimeout(() => updateButton(), 3000);
    }

    // Resume collection if we were in the middle of auto-collecting
    function checkResumeCollection() {
        const wasCollecting = localStorage.getItem('meli_collecting') === 'true';

        if (wasCollecting) {
            const savedData = localStorage.getItem('meli_collected_data');
            const savedTotal = parseInt(localStorage.getItem('meli_total_pages')) || 1;

            if (savedData) {
                allFavorites = JSON.parse(savedData);
            }

            // IMPORTANT: Trust the URL for current page, trust localStorage for total pages
            const urlParams = new URLSearchParams(window.location.search);
            currentPage = parseInt(urlParams.get('page')) || 1;
            totalPages = savedTotal;  // Always trust the saved total from page 1

            console.log(`Resuming collection: page ${currentPage}/${totalPages}, ${allFavorites.length} items so far`);

            // Safety check: prevent infinite loops
            if (currentPage === lastCollectedPage) {
                console.error(`⚠ Safety stop: Already collected page ${currentPage}. Navigation might be broken.`);
                alert(`Collection stopped at page ${currentPage}/${totalPages} - navigation appears to be stuck.\n\nCollected ${allFavorites.length} items so far.`);
                finishCollection();
                return;
            }

            isCollecting = true;
            lastCollectedPage = currentPage;

            // Collect current page
            const currentFavorites = extractFavoritesFromPage();
            allFavorites.push(...currentFavorites);

            console.log(`Collected ${currentFavorites.length} items from page ${currentPage}`);
            updateButton(`Collecting page ${currentPage}/${totalPages}... (${allFavorites.length} items)`);

            // Check if done
            if (currentPage >= totalPages) {
                console.log(`✓ Reached final page ${currentPage}/${totalPages} - finishing collection`);
                finishCollection();
                return;
            }

            // Update stored data
            localStorage.setItem('meli_collected_data', JSON.stringify(allFavorites));
            localStorage.setItem('meli_current_page', currentPage.toString());

            // Continue to next page
            console.log(`→ Going to page ${currentPage + 1}/${totalPages}...`);
            setTimeout(() => {
                goToNextPage();
            }, 1500);  // Slightly longer delay to be safe
        }
    }

    // Create floating button UI
    function createButton() {
        const pagination = getPaginationInfo();
        currentPage = pagination.current;
        totalPages = pagination.total;

        const container = document.createElement('div');
        container.id = 'meli-exporter-container';
        container.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            z-index: 9999;
            background: #1e1e1e;
            padding: 16px;
            border: 2px solid #00d9ff;
            border-radius: 4px;
            box-shadow: 0 4px 12px rgba(0, 217, 255, 0.2);
            font-family: "Fira Code", "JetBrains Mono", Consolas, monospace;
            color: #e0e0e0;
            min-width: 280px;
        `;

        const hasNextPage = !!findNextButton();
        const statusText = totalPages > 1
            ? `Page ${currentPage}/${totalPages}`
            : hasNextPage
                ? `Page ${currentPage} (more pages available)`
                : `Page ${currentPage} (last page)`;

        container.innerHTML = `
            <div style="
                font-weight: 600;
                margin-bottom: 8px;
                font-size: 13px;
                color: #00d9ff;
                letter-spacing: 0.5px;
            ">
                ╭─ MERCADOLIVRE → HOLOCENE
            </div>
            <div id="meli-status" style="
                font-size: 12px;
                margin-bottom: 12px;
                color: #888;
                font-family: monospace;
            ">
                │ ${statusText}
            </div>
            <button id="meli-export-current" style="
                width: 100%;
                padding: 10px 12px;
                margin-bottom: 6px;
                background: transparent;
                border: 1px solid #555;
                border-radius: 3px;
                color: #aaa;
                cursor: pointer;
                font-size: 12px;
                font-family: inherit;
                text-align: left;
                transition: all 0.15s;
            ">
                ├─ Export current page
            </button>
            <button id="meli-export-all" style="
                width: 100%;
                padding: 10px 12px;
                background: #00d9ff;
                border: none;
                border-radius: 3px;
                color: #000;
                cursor: pointer;
                font-size: 12px;
                font-weight: 600;
                font-family: inherit;
                text-align: left;
                transition: all 0.15s;
            ">
                └─ Auto-collect all pages
            </button>
        `;

        document.body.appendChild(container);

        // Add hover effects
        const btnCurrent = document.getElementById('meli-export-current');
        const btnAll = document.getElementById('meli-export-all');

        btnCurrent.onmouseenter = () => {
            btnCurrent.style.borderColor = '#00d9ff';
            btnCurrent.style.color = '#00d9ff';
        };
        btnCurrent.onmouseleave = () => {
            btnCurrent.style.borderColor = '#555';
            btnCurrent.style.color = '#aaa';
        };

        btnAll.onmouseenter = () => {
            btnAll.style.background = '#00f0ff';
            btnAll.style.transform = 'translateX(2px)';
        };
        btnAll.onmouseleave = () => {
            btnAll.style.background = '#00d9ff';
            btnAll.style.transform = 'translateX(0)';
        };

        // Attach handlers
        document.getElementById('meli-export-current').onclick = exportCurrentPage;
        document.getElementById('meli-export-all').onclick = () => {
            const hasNext = findNextButton();
            const message = hasNext
                ? 'This will automatically navigate through ALL pages and collect your favorites.\n\nIt may take 1-2 minutes depending on how many pages you have.\n\nContinue?'
                : 'This appears to be the last page. Do you want to export just this page?';

            if (confirm(message)) {
                autoCollectAllPages();
            }
        };

        return container;
    }

    // Update button text
    function updateButton(text) {
        const status = document.getElementById('meli-status');
        if (status) {
            if (text) {
                status.textContent = `│ ${text}`;
            } else {
                const pagination = getPaginationInfo();
                const hasNext = !!findNextButton();
                const statusText = pagination.total > 1
                    ? `Page ${pagination.current}/${pagination.total}`
                    : hasNext
                        ? `Page ${pagination.current} (more pages available)`
                        : `Page ${pagination.current} (last page)`;
                status.textContent = `│ ${statusText}`;
            }
        }
    }

    // Wait for pagination to be rendered (SPA delay)
    function waitForPagination(callback, attempts = 0) {
        const maxAttempts = 10;
        const pagination = document.querySelector('.andes-pagination');

        if (pagination || attempts >= maxAttempts) {
            console.log(pagination ? '✓ Pagination found' : '⚠ Pagination not found after waiting');
            callback();
        } else {
            console.log(`Waiting for pagination to load... (attempt ${attempts + 1}/${maxAttempts})`);
            setTimeout(() => waitForPagination(callback, attempts + 1), 500);
        }
    }

    // Initialize when page loads
    function init() {
        // Wait for page to be fully loaded
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', init);
            return;
        }

        // Wait for pagination to be rendered (SPA)
        waitForPagination(() => {
            // Check if we're resuming a collection
            checkResumeCollection();

            // Create button if not already collecting
            if (!isCollecting) {
                createButton();
            }
        });
    }

    init();
})();
