var TEMPERATUREHIGHLIMIT = 25.0;
var TEMPERATUREHIGHWARNING = 24.0;
var TEMPERATURELOWWARNING = 19.0;
var TEMPERATURELOWLIMIT = 18.0;
var HUMIDITYHIGHLIMIT = 70.0;
var HUMIDITYHIGHWARNING = 65.0;
var HUMIDITYLOWWARNING = 30.0;
var HUMIDITYLOWLIMIT = 15.0;

$(document).ready(function () {

    $(".datepicker").datepicker().on("changeDate", function () {
        $(this).datepicker('hide'); //Todo: implement check to ensure from < to
    });

    // Updates modal and shows it
    $(".time-filter-select").click(function () {
        updateModalContents(null);
    });

    $(".data-export").click(function () {
        let modal = $("#measurementHistoryModal");
        let context = {
            deviceSn: "test",
            exportFormat: $(this).attr("format"),
        };

        getHistoricalDeviceReadings(context, function (context, data) {
            let filename = `metrology_export_${context.deviceSn}_${context.deviceLocation}_${formatDatetimeForFilename(context.from)}_to_${formatDatetimeForFilename(context.to)}.csv`;
            saveData(data, filename);
        });
    });
});

function convert12hrTo24hr(hour, isPm) {
    let hour24 = parseInt(hour) === 12 ? 0 : parseInt(hour);
    return isPm ? hour24 + 12 : hour24;
}

function getDateObjFromPicker(parentSelector, classSelector) {
    // let dateObj = new Date($(parentSelector).find(classSelector + ".date").datepicker('getDate'));
    let dateObj = new Date($(parentSelector).find(classSelector + ".date").datepicker('getDate'));
    dateObj.setHours(
        convert12hrTo24hr($(parentSelector).find(classSelector + ".hours").val(), $(parentSelector).find(classSelector + ".is-pm").val() === "True"),
        $(parentSelector).find(classSelector + ".minutes").val(),
        0,
        0
    );

    return dateObj;
}

function formatDatetimeForFilename(dateObj) {
    let year = dateObj.getFullYear().toString();
    let month = (dateObj.getMonth() + 1).toString().padStart(2, '0');
    let date = dateObj.getDate().toString().padStart(2, '0');
    let hours = dateObj.getHours().toString().padStart(2, '0');
    let minutes = dateObj.getMinutes().toString().padStart(2, '0');
    let seconds = dateObj.getSeconds().toString().padStart(2, '0');
    return `${year}-${month}-${date}T${hours}_${minutes}_${seconds}Z`;
}

// Request all data for deviceSn given in the context between the datetimes in the modal's form
// Form data is contained within the POST
function getHistoricalDeviceReadings(context, callback) {
    let form = $("#modal-filter");
    let url = `//${location.host}/pulogger/getHistory/?device=${context.deviceSn}`;

    url += `&clientTzOffset=${new Date().getTimezoneOffset()}`;

    if ("exportFormat" in context) {
        url += `&format=${context.exportFormat}`;
    }

    $.ajax({
        type: form.attr("type"),
        url: url,
        data: form.serialize(),
        success: function (responseData) {
            context.from = getDateObjFromPicker("#modal-filter", ".from");
            context.to = getDateObjFromPicker("#modal-filter", ".to");
            callback(context, responseData);
        }
    });
}

function renderChart(context, dataJson) {
    var chart = new CanvasJS.Chart("chartContainer", {
        theme: "light1", // "light2", "dark1", "dark2"
        animationEnabled: true, // change to true
        title: {
            text: context.location
        },
        axisX: {
            valueFormatString: "DD MMM HH:mm"
        },
        axisY: {
            title: "Temperature",
            prefix: "",
            suffix: "°C",
            maximum: 34,
            minimum: 16
        },
        axisY2: {
            title: "Relative Humidity",
            prefix: "",
            suffix: "%"
        },
        toolTip: {
            shared: true
        },
        legend: {
            cursor: "pointer",
            verticalAlign: "top",
            horizontalAlign: "center",
            dockInsidePlotArea: false,
            // itemclick: toggleDataSeries
        },
        data: dataJson
    });

    chart.render();

}

// Refresh modal and show, if necessary
function updateModalContents(deviceSn) {
    let modal = $("#measurement-history-modal");
    if (deviceSn == null) {  // if modal is updating due to new time filter
        deviceSn = $(modal).attr("active-device");
    }

    let device = $(`#${deviceSn}`);
    let deviceLocation = $(device).find(".room-number").html();

    if (deviceSn != null) {  // if modal was just launched for a new device
        $(modal).attr("active-device", deviceSn);
        $(modal).attr("active-device-location", deviceLocation);
    }

    let context = {
        deviceSn: deviceSn,
    };

    getHistoricalDeviceReadings(context, function (context, responseData) {
        let dataJson = JSON.parse(responseData);
        $(modal).find(".modal-title").text(`Measurement History: Device ${deviceSn}`);

        if ($(modal).is(":visible")) {
            renderChart(context, dataJson);
        } else {
            //delay chart render until modal has been drawn, to enable CanvasJS stretch-to-fit
            $(modal).on('shown.bs.modal', function () {
                renderChart(context, dataJson);
                $(modal).off('shown.bs.modal');
            });
            $(modal).modal("show");
        }
    });
}

// Prompt download of a file by creating a Blob with the file contents,
// creating a URL for it, and using the download attribute.
function saveData(data, fileName) {
    const a = document.createElement("a");
    document.body.appendChild(a);
    a.style = "display: none";

    const blob = new Blob([data], {type: "octet/stream"}),
        url = window.URL.createObjectURL(blob);

    a.href = url;
    a.download = fileName;
    a.click();
    window.URL.revokeObjectURL(url);
    a.remove();
}