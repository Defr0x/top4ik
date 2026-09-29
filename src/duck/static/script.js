$(document).ready(function(){
    $('#67').on('submit',function(e){
        e.preventDefault();
        err = 0;
        if ($('#fullname').val().trim() === '' || $('#password').val().trim() != $('#confirm_password').val().trim()){
            err = 1;
        }else{
            err = 0;
        }
        if (err == 0){
            $.ajax({
                url: '/user_register',
                method: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({
                    name: $('#fullname').val(),
                    password: $('#password').val(),
                    email: $('#email').val()
                })
            }).done(function(){
                window.location.href="/login"
            })
        }
    })
})
$(document).ready(function(){
    $('#333').on('submit', function(e){
        e.preventDefault();
        err = 0;
        if ($('#email').val().trim() === '' || $('#password').val().trim() === ''){
            err = 1;
        }else{
            err = 0;
        }
        if (err == 0){
            $.ajax({
                url: '/user_login',
                method: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({
                    email: $('#email').val(),
                    password: $('#password').val()
                })
            }).done(function(response){
                window.location.href="/"
            }).fail(function(xhr){
                alert(xhr.responseJSON?.error || 'Ошибка входа');
            })
        }
    })
})
async function loginUser(email, password) {
    const response = await fetch('/user_login', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ email: email, password: password })
    });

    const data = await response.json();

    if (response.ok && data.redirect_url) {
        // Перенаправляем пользователя на дашборд!
        window.location.href = data.redirect_url;
    } else {
        alert(data.error || 'Ошибка входа');
    }
}