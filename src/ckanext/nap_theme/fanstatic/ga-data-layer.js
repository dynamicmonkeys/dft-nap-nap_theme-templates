function getSearchParameters() {
    var prmstr = window.location.search.substr(1);
    return prmstr != null && prmstr != "" ? transformToAssocArray(prmstr) : {};
  }
  
  function transformToAssocArray( prmstr ) {
    var params = {};
    var prmarr = prmstr.split("&");
    for ( var i = 0; i < prmarr.length; i++) {
        var tmparr = prmarr[i].split("=");
        params[tmparr[0]] = tmparr[1];
    }
    return params;
  }

  function pushSearchParamsToDatalayer() {
    console.log(getSearchParameters());
    params = getSearchParameters();
    for (key in params) {
        window.dataLayer.push({[key]: params[key]})
    };
  }

  function pushFormErrorsToDatalayer() {
      let json_errors = document.getElementById('errors_list').getAttribute('value').replace(/'/g, '"');
      let errors = JSON.parse(json_errors);
    for (key in errors) {
        window.dataLayer.push({[key]: errors[key]})
    }
  }
