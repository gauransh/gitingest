// Copy functionality
function copyText(className) {
    const textarea = document.querySelector('.' + className);
    const button = document.querySelector(`button[onclick="copyText('${className}')"]`);
    if (!textarea || !button) return;

    // Copy text
    navigator.clipboard.writeText(textarea.value)
        .then(() => {
            // Store original content
            const originalContent = button.innerHTML;

            // Change button content
            button.innerHTML = 'Copied!';

            // Reset after 1 second
            setTimeout(() => {
                button.innerHTML = originalContent;
            }, 1000);
        })
        .catch(err => {
            // Show error in button
            const originalContent = button.innerHTML;
            button.innerHTML = 'Failed to copy';
            setTimeout(() => {
                button.innerHTML = originalContent;
            }, 1000);
        });
}


function handleSubmit(event, showLoading = false) {
    event.preventDefault();
    
    // Get form and elements
    const form = document.getElementById('ingestForm');
    const gitUsername = document.getElementById('git_username');
    const gitPat = document.getElementById('git_pat');
    const slider = document.getElementById('file_size');
    
    // Create FormData
    const formData = new FormData(form);
    
    // Add required fields
    formData.set('max_file_size', slider ? slider.value : '50');
    formData.set('slider_position', slider ? slider.value : '50');
    
    // Update credentials if they exist
    if (gitUsername && gitPat) {
        const usernameValue = gitUsername.value.trim();
        const patValue = gitPat.value.trim();
        
        // Update hidden fields
        document.getElementById('git_username_hidden').value = usernameValue;
        document.getElementById('git_pat_hidden').value = patValue;
        
        // Update formData
        formData.set('git_username', usernameValue);
        formData.set('git_pat', patValue);
    }

    // Show loading state if requested
    if (showLoading) {
        document.getElementById('loading')?.classList.remove('hidden');
    }

    // Send the request
    fetch('/', {
        method: 'POST',
        body: formData
    })
    .then(response => response.text())
    .then(html => {
        document.documentElement.innerHTML = html;
        if (showLoading) {
            document.getElementById('loading')?.classList.add('hidden');
        }
    })
    .catch(error => {
        console.error('Error:', error);
        if (showLoading) {
            document.getElementById('loading')?.classList.add('hidden');
        }
    });
}

function copyFullDigest() {
    const directoryStructure = document.querySelector('.directory-structure').value;
    const filesContent = document.querySelector('.result-text').value;
    const fullDigest = `${directoryStructure}\n\nFiles Content:\n\n${filesContent}`;
    const button = document.querySelector('[onclick="copyFullDigest()"]');
    const originalText = button.innerHTML;

    navigator.clipboard.writeText(fullDigest).then(() => {
        button.innerHTML = `
            <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
            </svg>
            Copied!
        `;

        setTimeout(() => {
            button.innerHTML = originalText;
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy text: ', err);
    });
}

// Add the logSliderToSize helper function
function logSliderToSize(position) {
    const minp = 0;
    const maxp = 500;
    const minv = Math.log(1);
    const maxv = Math.log(102400);

    const value = Math.exp(minv + (maxv - minv) * Math.pow(position / maxp, 1.5));
    return Math.round(value);
}

// Move slider initialization to a separate function
function initializeSlider() {
    const slider = document.getElementById('file_size');
    const sizeValue = document.getElementById('size_value');

    if (!slider || !sizeValue) return;

    function updateSlider() {
        const value = logSliderToSize(slider.value);
        sizeValue.textContent = formatSize(value);
        slider.style.backgroundSize = `${(slider.value / slider.max) * 100}% 100%`;
    }

    // Update on slider change
    slider.addEventListener('input', updateSlider);

    // Initialize slider position
    updateSlider();
}

// Add helper function for formatting size
function formatSize(sizeInKB) {
    if (sizeInKB >= 1024) {
        return Math.round(sizeInKB / 1024) + 'mb';
    }
    return Math.round(sizeInKB) + 'kb';
}

// Initialize slider on page load
document.addEventListener('DOMContentLoaded', initializeSlider);

// Make sure these are available globally
window.copyText = copyText;

window.handleSubmit = handleSubmit;
window.initializeSlider = initializeSlider;
window.formatSize = formatSize;

// Add this new function
function setupGlobalEnterHandler() {
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' && !event.target.matches('textarea')) {
            const form = document.getElementById('ingestForm');
            if (form) {
                handleSubmit(new Event('submit'), true);
            }
        }
    });
}

// Add to the DOMContentLoaded event listener
document.addEventListener('DOMContentLoaded', () => {
    initializeSlider();
    setupGlobalEnterHandler();
});
