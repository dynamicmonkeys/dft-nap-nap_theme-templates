function openDeleteConfirm(target_id) {
    deleteConfirmContainer = document.getElementById(target_id);
    deleteConfirmContainer.style.maxHeight = deleteConfirmContainer.scrollHeight + "px";
}

function closeDeleteConfirm(target_id) {
    deleteConfirmContainer = document.getElementById(target_id);
    deleteConfirmContainer.style.maxHeight = null;
}

window.addEventListener("DOMContentLoaded", function () {
    $(".confirm-delete-form").each(function () {
        $(this).submit(function(e) {
            e.preventDefault(); 
            var form = $(this);
            var url = form.attr('action');
            $.ajax({
                type: "POST",
                url: '/api/3/action/package_delete',
                data: form.serialize(), 
                success: function(data)
                {
                    location.reload();
                }
            });
        });
    });
})