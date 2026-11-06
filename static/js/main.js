/**
 * Community Help Connect - Client JavaScript
 * Interactive helpers, form safety checks, and auto-dismiss alerts
 */

document.addEventListener('DOMContentLoaded', function () {
    // 1. Auto-dismiss flash alert messages after 6 seconds
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(function (alert) {
        setTimeout(function () {
            try {
                const bsAlert = new bootstrap.Alert(alert);
                bsAlert.close();
            } catch (e) {
                // If already closed manually
            }
        }, 6000);
    });

    // 2. Minimum Date Restriction (Prevent setting deadlines/expiry in the past)
    const today = new Date().toISOString().split('T')[0];
    const dateInputs = document.querySelectorAll('input[type="date"]');
    dateInputs.forEach(function (input) {
        if (!input.getAttribute('min')) {
            input.setAttribute('min', today);
        }
    });

    // 3. Category change helper for Surplus Food Sharing
    const categorySelect = document.getElementById('category');
    const expiryDateField = document.getElementById('expiry_date');
    if (categorySelect && expiryDateField) {
        const toggleExpiryHighlight = function () {
            const isFood = categorySelect.value.toLowerCase().includes('food');
            const parentGroup = expiryDateField.closest('.mb-3') || expiryDateField.parentElement;
            if (isFood) {
                if (parentGroup) parentGroup.classList.add('border', 'border-warning', 'p-2', 'rounded', 'bg-warning', 'bg-opacity-10');
            } else {
                if (parentGroup) parentGroup.classList.remove('border', 'border-warning', 'p-2', 'rounded', 'bg-warning', 'bg-opacity-10');
            }
        };
        categorySelect.addEventListener('change', toggleExpiryHighlight);
        toggleExpiryHighlight();
    }

    // 4. Form Submission Confirmation Dialogs
    const confirmForms = document.querySelectorAll('form[data-confirm]');
    confirmForms.forEach(function (form) {
        form.addEventListener('submit', function (e) {
            const message = form.getAttribute('data-confirm') || 'Are you sure you want to proceed with this action?';
            if (!confirm(message)) {
                e.preventDefault();
            }
        });
    });

    // Show progress while a document upload is being validated and stored.
    const loadingForms = document.querySelectorAll('form[data-loading-form]');
    loadingForms.forEach(function (form) {
        form.addEventListener('submit', function (e) {
            if (e.defaultPrevented) return;

            const button = form.querySelector('button[type="submit"], input[type="submit"]');
            if (!button) return;

            const label = form.getAttribute('data-loading-text') || 'Please wait...';
            button.disabled = true;
            const status = document.createElement('span');
            status.className = 'visually-hidden';
            status.setAttribute('role', 'status');
            status.textContent = label;
            form.append(status);

            if (button instanceof HTMLInputElement) {
                button.value = label;
                return;
            }

            button.textContent = label;
            const spinner = document.createElement('span');
            spinner.className = 'spinner-border spinner-border-sm me-2';
            spinner.setAttribute('role', 'status');
            spinner.setAttribute('aria-hidden', 'true');
            button.prepend(spinner);
        });
    });

    // 5. Tooltip Initialization
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
});
