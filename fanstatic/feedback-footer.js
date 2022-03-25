var feedbackButtons = document.getElementsByClassName("feedback-button");
var feedbackAlert = document.getElementById("feedback-alert");
var feedbackButtonSection = document.getElementById("feedback-footer-buttons");


for (feedbackButton of feedbackButtons) {
    feedbackButton.addEventListener("click", function(event) {
        feedbackButtonSection.classList.add("js-hidden");
        feedbackAlert.classList.remove("js-hidden");
    });
}
