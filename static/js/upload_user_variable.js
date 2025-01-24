document.addEventListener('DOMContentLoaded', () => {
	const keysEndpoint = '/get_existing_tags'; // Updated to use the correct endpoint
	const interactiveKeyDropdown = document.getElementById('interactive-key-dropdown');
	const interactiveNewInput = document.getElementById('interactive-new-input');
	const interactiveExistingDropdown = document.getElementById('interactive-existing-dropdown');
	const newRadio = document.getElementById('new-value-radio');
	const existingRadio = document.getElementById('existing-value-radio');
	const addButton = document.getElementById('add-key-value-pair');
	const staticSection = document.getElementById('static-section');

	// Fetch and populate keys and their initial values
	fetch(keysEndpoint)
		.then(response => {
			if (!response.ok) {
				throw new Error(`HTTP error ${response.status}`);
			}
			return response.json();
		})
		.then(keysAndValues => {
			// Populate the keys dropdown
			const keys = Object.keys(keysAndValues);
			interactiveKeyDropdown.innerHTML = keys.map(key => `<option value="${key}">${key}</option>`).join('');

			// Populate values for the first key, if available
			if (keys.length > 0) {
				loadExistingValues(keys[0], keysAndValues[keys[0]]);
			}
		})
		.catch(error => {
			console.error('Error fetching keys and values:', error);
		});

	// Function to populate values for the selected key
	function loadExistingValues(key, values) {
		if (!values || !Array.isArray(values)) {
			values = [];
		}
		interactiveExistingDropdown.innerHTML = values
			.map(value => `<option value="${value.trim()}">${value.trim()}</option>`)
			.join('');
	}
	
	function saveKeyValuePairs() {
		const keyValuePairs = [];
		document.querySelectorAll('.static-row').forEach(row => {
			const key = row.querySelector('label:first-child').textContent.replace('Key: ', '');
			const value = row.querySelector('label:nth-child(2)').textContent.replace('Value: ', '');
			keyValuePairs.push({ key, value });
		});
		localStorage.setItem('keyValuePairs', JSON.stringify(keyValuePairs));
	}

	// Update the values dropdown when a new key is selected
	interactiveKeyDropdown.addEventListener('change', () => {
		const selectedKey = interactiveKeyDropdown.value;

		// Re-fetch all keys and values to get updated values for the selected key
		fetch(keysEndpoint)
			.then(response => response.json())
			.then(keysAndValues => {
				const values = keysAndValues[selectedKey] || [];
				loadExistingValues(selectedKey, values);
			})
			.catch(error => console.error(`Error fetching values for key ${selectedKey}:`, error));
	});

	// Toggle between new and existing value inputs
	newRadio.addEventListener('change', () => {
		interactiveNewInput.disabled = false;
		interactiveExistingDropdown.disabled = true;
	});

	existingRadio.addEventListener('change', () => {
		interactiveNewInput.disabled = true;
		interactiveExistingDropdown.disabled = false;
	});

	// Add a new key-value pair to the static section
	addButton.addEventListener('click', () => {
		const key = interactiveKeyDropdown.value;
		const value = newRadio.checked ? interactiveNewInput.value : interactiveExistingDropdown.value;

		if (!value) {
			alert("Please enter or select a value!");
			return;
		}

		// Check if the key already exists in the static section
		const existingRow = Array.from(staticSection.children).find(row =>
			row.querySelector('label:first-child').textContent.includes(`Key: ${key}`)
		);

		if (existingRow) {
			// Update the existing row's value
			const valueLabel = existingRow.querySelector('label:nth-child(2)');
			valueLabel.textContent = `Value: ${value}`;
			saveKeyValuePairs();
		} else {
			// Add a new row
			const staticRow = document.createElement('div');
			staticRow.classList.add('static-row');
			staticRow.innerHTML = `
				<label>Key: ${key}</label>
				<label>Value: ${value}</label>
				<button class="remove-row">Remove</button>
			`;
			staticSection.appendChild(staticRow);
			saveKeyValuePairs();

			// Add event listener to remove the row
			staticRow.querySelector('.remove-row').addEventListener('click', () => {
				staticRow.remove();
				saveKeyValuePairs();
			});
		}

		// Clear inputs in the interactive section for the next entry
		interactiveNewInput.value = '';
		if (newRadio.checked) interactiveNewInput.focus();
	});
	
});

