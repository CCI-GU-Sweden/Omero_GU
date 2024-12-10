const upload = {

    fetchProjects: function(projectDropdown) {
        fetch("/get_projects", {
            method: 'POST',
            body: ""
        })
        .then(response => response.json())
        .then(data => {
            data.forEach(project => {
                projectDropdown.innerHTML = '';
                const option = document.createElement('option');
                option.value = project[1];
                option.textContent = project[0];
                projectDropdown.appendChild(option);
            });
        })
        .catch(error => console.error('Error:', error));
    }
};