export function fetchWrapper(endPointName) {
    return fetch(endPointName)
    .then(response => {
        if(!response.ok) {
            return response.json().then(errorData => {
                throw errorData;
            });
        }
        return response.json();
    })
    .catch(error => {
        console.error("customFetch error ",error.message);
        return Promise.reject({
            error: true,
            message: error.message,
            status: error.response ? error.response.status : 'unknown'
        });
    })
};
    


const utils = {

    log: (function() {

        function doLog(logLevel, message){
            const logData = {
                level: logLevel,
                message: message 
            }
            fetch("/log", {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json' 
                },
                body: JSON.stringify(logData)
                }
            )
            .catch(error => console.error('Error:', error))
        }

        return {
            info: function(message) {
                doLog('info',message);    
            },
            debug: function(message) {
                doLog('debug',message);    
            }   
        };
    })()
};