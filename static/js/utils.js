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
            type:error.error,
            message: error.message,
            status: error.response ? error.response.status : 'unknown'
        });
    })
};
  
export function showErrorPage(type,msg) { 
    const encodedType = encodeURIComponent(type);
    const encodedMsg = encodeURIComponent(msg);

    window.location.href =`/error_page?error_type=${encodedType}&message=${encodedMsg}`;

};

export function pairFiles(fileList, ext1, ext2) //not used anymore, replaced by buildPairs in file_list.js
{
    var ext1List = Array.from(fileList).filter((file) => file.name.split('.').pop() === ext1)
    var ext2List = Array.from(fileList).filter((file) => file.name.split('.').pop() === ext2)

    var resList = [];
    for(var f1 of ext1List)
    {
        var f1Name = f1.name.split('.')[0];
        var filePair = {ext1: f1, ext2: null};
        var f2 = ext2List.find((file) => file.name.includes(f1Name))
        if( f2 )
        {
            filePair.ext2 = f2;
            var idx = ext2List.indexOf(f2);
            ext2List.splice(idx,1);
        }

        resList.push(filePair);
    }

    //check if we have remaining unmatches files in ext2list
    for(var f in ext2List)
    {
        filePair = {ext1: null, ext2: f};
        resList.push(filePair);
    }

    return resList;
}

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