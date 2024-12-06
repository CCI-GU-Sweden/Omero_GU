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